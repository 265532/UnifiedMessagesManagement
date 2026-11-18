"""钉钉长连接（Stream 模式）入站通道。

为什么要有这个文件
------------------
之前系统收消息只有一条入口：POST /webhook/<platform>。这条路要求平台主动
把消息 POST 到你的机器上，那就得有个公网能访问的地址——公网 IP、域名，
或者内网穿透工具，缺一不可。本机没有公网，所以「真人从手机发一条消息、
系统真的收到」这件事一直做不到，演示时只能靠模拟数据。

钉钉的 Stream 模式把方向反过来了：程序主动去连钉钉网关，保持一条 WebSocket。
群里有人 @机器人 说话，钉钉就从这条已经连好的长连接上把消息推下来。
不需要公网 IP，不需要开端口，也不需要备案。

同一个系统，两条入口，后面共用一套处理逻辑
-----------------------------------------
    /webhook/dingtalk   →  service.receive(..., trusted=False)  走 timestamp + sign 验签
    Stream 长连接        →  service.receive(..., trusted=True)   靠建连时的 ticket 认证

解析、格式校验、幂等去重、入库、推前端、状态流转全部复用，没有第二套代码。
"""

import asyncio
import threading
import time

import config
from core import service


def _build_client(on_payload):
    """把 SDK 的导入都关在这个函数里。

    没装 dingtalk-stream 的时候，只要不开长连接开关，启动、网页、发送这些功能
    一点都不受影响，不会因为一个可选通道把整个项目拖挂。真要用的时候导入失败，
    异常会在这里抛出来，由调用方翻译成人话提示。

    返回 (client, sdk 模块)，模块给上层拿常量用。
    """
    import dingtalk_stream
    from dingtalk_stream import AckMessage, ChatbotHandler, Credential, DingTalkStreamClient
    from dingtalk_stream.chatbot import ChatbotMessage

    class _BotHandler(ChatbotHandler):
        """收到机器人消息后做的事：转给统一入口，然后回 ACK。

        ACK 是给钉钉看的回执，意思是「这条我处理完了，别再推一遍」。
        处理本身丢到线程里跑（asyncio.to_thread），因为要写 SQLite，
        写库是同步操作，直接压在事件循环上会卡住这条连接上的后续消息。
        """

        async def process(self, callback):
            payload = callback.data or {}
            try:
                await asyncio.to_thread(on_payload, payload)
            except Exception as e:          # noqa: BLE001
                self.logger.exception("处理机器人消息失败: %s", e)
                # 返回非 200 让钉钉知道没处理成功，便于在后台看到异常
                return AckMessage.STATUS_SYSTEM_EXCEPTION, f"处理失败：{e}"
            return AckMessage.STATUS_OK, "OK"

    client = DingTalkStreamClient(
        Credential(
            client_id=config.DINGTALK["app_key"],
            client_secret=config.DINGTALK["app_secret"],
        )
    )
    # 只订阅「机器人消息」这一个 topic。群聊里要 @机器人 才会触发，单聊直接发就行。
    client.register_callback_handler(ChatbotMessage.TOPIC, _BotHandler())
    return client, dingtalk_stream


class DingTalkStreamRunner:
    """长连接的生命周期管理。

    对外只暴露三件事：能不能启动、启动、现在什么状态。
    start() 起一个后台线程，线程里跑 SDK 自带的「断线自动重连」循环。
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self.running = False
        self.last_error = ""
        self.last_message_at = ""
        self.received_count = 0

    # ---------------------------------------------------------------- 前置检查
    def missing_reason(self) -> str:
        """返回「还缺什么」，空字符串表示条件齐了。"""
        if not config.DINGTALK.get("app_key") or not config.DINGTALK.get("app_secret"):
            return ("缺 DINGTALK_APP_KEY / DINGTALK_APP_SECRET。"
                    "这里要企业内部应用的 ClientID 和 ClientSecret，"
                    "不是群自定义机器人的 Webhook，两者不是一回事。")
        try:
            import dingtalk_stream  # noqa: F401
        except ImportError:
            return "没装 dingtalk-stream 包，执行 pip install dingtalk-stream"
        return ""

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True

        reason = self.missing_reason()
        if reason:
            self.last_error = reason
            print(f"[dingtalk-stream] 未启动：{reason}")
            return False

        self._thread = threading.Thread(target=self._run, name="dingtalk-stream", daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        """线程主体。SDK 的 start_forever 内部自己处理重连，外面这层只兜底异常。"""
        while True:
            try:
                client, _ = _build_client(self._handle_payload)
                self.running = True
                self.last_error = ""
                print("[dingtalk-stream] 正在连接钉钉网关 ...")
                client.start_forever()
            except Exception as e:          # noqa: BLE001
                self.running = False
                self.last_error = f"{type(e).__name__}: {e}"
                print(f"[dingtalk-stream] 连接中断，10 秒后重试：{self.last_error}")
                time.sleep(10)

    # ---------------------------------------------------------------- 消息处理
    def _handle_payload(self, payload: dict) -> None:
        """长连接推下来的一条原始消息，直接进统一入口。

        payload 是钉钉机器人消息的原始格式（senderNick / senderId /
        conversationId / conversationTitle / msgtype / text.content / msgId），
        和 /webhook/dingtalk 收到的 body 是同一套字段，所以 adapter.parse 不用改。
        """
        self.last_message_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.received_count += 1
        service.receive("dingtalk", payload, {}, trusted=True)

    def status(self) -> dict:
        """给 /healthz 用。开着开关却没跑起来的时候，missing 会写清楚卡在哪。"""
        return {
            "enabled": config.DINGTALK_STREAM_ENABLED,
            "running": self.running,
            "missing": self.missing_reason(),
            "last_error": self.last_error,
            "last_message_at": self.last_message_at,
            "received_count": self.received_count,
        }


_runner: DingTalkStreamRunner | None = None


def get_runner() -> DingTalkStreamRunner:
    """全局单例。app.py 启动时拿它拉起连接，/healthz 拿它看状态。"""
    global _runner
    if _runner is None:
        _runner = DingTalkStreamRunner()
    return _runner
