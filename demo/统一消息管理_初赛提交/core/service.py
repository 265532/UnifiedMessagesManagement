"""核心服务层。

所有业务动作都从这里进，Adapter 只负责跟平台通信。
一条消息走完的流程：

    接收 → 验签 → 解析 → 格式校验 → 去重入库 → 推送前端 → 展示 → 处理 → 回复 → 发送 → 回执确认

每一步都会往事件总线发一条 pipeline 事件，前端据此按顺序点亮流程图上的节点。
"""

import time
import uuid

import config
from adapters.dingtalk import DingTalkAdapter
from adapters.feishu import FeishuAdapter
from adapters import mock_feed
from core import bus, schema, state_machine, store
from core.schema import now_iso

# 适配器注册表。加企业微信时，这里挂一个 WeComAdapter 就行。
ADAPTERS = {
    "feishu": FeishuAdapter(),
    "dingtalk": DingTalkAdapter(),
}


class ReceiveError(Exception):
    """接收环节出错，携带出错阶段，方便前端定位。"""

    def __init__(self, stage: str, reason: str):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def _emit(stage: str, status: str, message_id: str = "", detail: str = "") -> None:
    bus.publish({
        "type": "pipeline",
        "stage": stage,
        "status": status,
        "message_id": message_id,
        "detail": detail,
        "at": now_iso(),
    })


# ------------------------------------------------------------------ 接收

def receive(platform: str, payload: dict, headers: dict | None = None,
            preparsed: bool = False, trusted: bool = False) -> dict:
    """处理一次平台回调。返回处理结果，给 webhook 接口直接响应。

    preparsed=True 表示 payload 已经是内部标准格式（模拟数据和测试用），
    不再走 adapter.parse，避免把标准格式当成平台原始事件再解析一遍。

    trusted=True 表示这条消息来自已经认证的长连接（钉钉 Stream）。
    HTTP 回调那套 timestamp + sign 签名是给「平台主动 POST 到你的公网地址」用的，
    长连接里根本没有这些 header，硬验会全部拒掉。长连接的身份在建立连接时
    用 clientSecret 换 ticket 就已经验过了，这里不必重复验。
    只有真的是已认证的长连接通道才能传 True，webhook 入口一律不传。
    """
    adapter = ADAPTERS.get(platform)
    if not adapter:
        _emit("verify", "fail", "", f"未知平台 {platform}")
        raise ReceiveError("verify", f"未知平台 {platform}")

    # 1. 验签
    _emit("verify", "start")
    if trusted:
        _emit("verify", "ok", "", "长连接通道，建连时已用 ticket 认证")
    elif not adapter.verify(payload, headers or {}):
        _emit("verify", "fail", "", "签名校验未通过")
        raise ReceiveError("verify", "签名校验未通过")
    else:
        _emit("verify", "ok")

    # 2. 解析成标准格式
    _emit("parse", "start")
    if preparsed:
        message = payload
    else:
        try:
            message = adapter.parse(payload)
        except Exception as e:
            _emit("parse", "fail", "", f"解析异常：{e}")
            raise ReceiveError("parse", f"解析异常：{e}")

    # 3. 格式校验。校验不过不丢，进 parse_failed 等人工处理
    ok, reason = schema.validate(message)
    if not ok:
        message["status"] = "parse_failed"
        store.insert_message(message)
        _emit("parse", "fail", message["id"], reason)
        bus.publish({"type": "message", "payload": message})
        return {"result": "parse_failed", "message_id": message["id"], "reason": reason}

    _emit("parse", "ok", message["id"])

    # 4. 幂等去重入库
    _emit("dedupe", "start", message["id"])
    inserted = store.insert_message(message)
    if not inserted:
        store.log_duplicate(message["event_id"])
        _emit("dedupe", "fail", message["id"], "重复事件，已丢弃")
        return {"result": "duplicate", "message_id": "", "reason": "同一平台事件已处理过"}

    _emit("dedupe", "ok", message["id"], "首次到达")

    # 5. 解析通过，状态推进到已入库
    message = store.transition(message["id"], "stored", "解析通过，去重后入库")
    _emit("store", "ok", message["id"])

    # 6. 推送前端
    _emit("push", "start", message["id"])
    bus.publish({"type": "message", "payload": message})
    _emit("push", "ok", message["id"])

    return {"result": "accepted", "message_id": message["id"], "status": message["status"]}


def receive_mock(platform: str | None = None) -> dict:
    """演示用：造一条模拟事件走完整接收流程。"""
    platform = platform or ("feishu" if time.time() % 2 < 1 else "dingtalk")
    payload = mock_feed.make_event(platform)
    return receive(platform, payload, {}, preparsed=True)


def duplicate_demo(platform: str) -> dict:
    """演示幂等：拿最近一条消息的 event_id 再投一次，应该被丢弃。"""
    messages = store.list_messages(platform=platform, limit=1)
    if not messages:
        return {"result": "empty", "reason": "该平台还没有消息"}

    dup = mock_feed.make_duplicate(platform, messages[0])
    return receive(platform, dup, {}, preparsed=True)


# ------------------------------------------------------------------ 展示与处理

def display(message_id: str) -> dict:
    """前端拉到这条消息了，状态从 stored 推进到 displayed。

    已经推进过的消息直接返回当前状态，不报错。前端会因为重复点击、
    SSE 刷新等原因多次调用，这种重复请求不该让用户看到红字。
    """
    message = store.get_message(message_id)
    if not message:
        raise KeyError(f"消息 {message_id} 不存在")
    if message["status"] != "stored":
        return message
    return store.transition(message_id, "displayed", "前端已展示该消息")


def process(message_id: str) -> dict:
    """用户读过了，标记为已处理。

    如果消息还停在 stored（用户直接从列表点了「标记已处理」，没经过详情页），
    先补一次展示，再推进到已处理，否则状态机会拒绝 stored→processed。
    """
    message = store.get_message(message_id)
    if not message:
        raise KeyError(f"消息 {message_id} 不存在")
    if message["status"] == "processed":
        return message
    if message["status"] == "stored":
        store.transition(message_id, "displayed", "用户打开详情，视为已展示")
    return store.transition(message_id, "processed", "用户已阅读并处理")


# ------------------------------------------------------------------ 回复发送

def reply(message_id: str, text: str, simulate_failure: bool = False) -> dict:
    """在统一入口回复一条消息，这整个动作就是闭环里最容易断的一环。

    步骤：状态进 replying → 调平台 API → 成功进 replied，失败进 send_failed 并重试。
    """
    message = store.get_message(message_id)
    if not message:
        raise KeyError(f"消息 {message_id} 不存在")

    adapter = ADAPTERS[message["platform"]]
    store.transition(message_id, "replying", f"提交回复：{text[:20]}…" if len(text) > 20 else f"提交回复：{text}")
    _emit("send", "start", message_id, f"发往{config.PLATFORM_LABEL[message['platform']]}")

    result = _send_with_retry(adapter, message, text, simulate_failure)

    if result["ok"]:
        # 群机器人 Webhook 只回 errcode，不返回消息 ID；空着就别写「ID：」留个空尾巴
        if result.get("platform_msg_id"):
            note = f"平台消息 ID：{result['platform_msg_id']}"
        else:
            note = "发送成功（群机器人通道不返回消息 ID）"
        updated = store.transition(message_id, "replied", note)
        _emit("send", "ok", message_id, "平台已受理")
        bus.publish({
            "type": "sent",
            "message_id": message_id,
            "platform_msg_id": result["platform_msg_id"],
            "text": text,
            "at": now_iso(),
        })
        return {"result": "replied", "message": updated, "platform_msg_id": result["platform_msg_id"]}

    # 重试耗尽，转死信等人工补发。
    # 这里不能从 replying 直接跳到 dead —— 状态机只允许 replying→send_failed→dead，
    # 少了中间那一步会直接抛 IllegalTransition，消息永远卡在「回复中」。
    _emit("send", "fail", message_id, result["error"])
    store.transition(message_id, "send_failed", f"发送失败：{result['error']}")
    updated = store.transition(message_id, "dead", "重试次数耗尽，转人工补发")
    return {"result": "dead", "message": updated, "error": result["error"]}


def _send_with_retry(adapter, message: dict, text: str, simulate_failure: bool) -> dict:
    """指数退避重试。对应 NFR-01：最多 5 次，间隔 0.5s 起逐次翻倍。"""
    last_error = ""
    for attempt in range(1, config.RETRY_MAX_TIMES + 1):
        if simulate_failure and attempt < 3:
            # 注入故障用：前两次故意失败，第三次成功，演示重试链路
            last_error = "模拟限流 429"
            store.log_note(message["id"], "send_retry", f"第 {attempt} 次失败：{last_error}，退避后重试")
            _emit("send", "retry", message["id"], f"第 {attempt} 次失败：{last_error}，退避后重试")
            time.sleep(config.RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            continue

        result = adapter.send(
            conversation_id=message["conversation"]["id"],
            msg_type="text",
            content={"text": text},
        )
        if result["ok"]:
            return result

        last_error = result["error"]
        if attempt < config.RETRY_MAX_TIMES:
            delay = config.RETRY_BASE_DELAY * (2 ** (attempt - 1))
            store.log_note(message["id"], "send_retry", f"第 {attempt} 次失败：{last_error}，{delay:.1f}s 后重试")
            _emit("send", "retry", message["id"], f"第 {attempt} 次失败：{last_error}，{delay:.1f}s 后重试")
            time.sleep(delay)

    return {"ok": False, "platform_msg_id": "", "error": last_error or "重试次数耗尽"}


def confirm(message_id: str) -> dict:
    """模拟平台回执回来，闭环走到最后一格。"""
    updated = store.transition(message_id, "confirmed", "平台回执已确认")
    _emit("receipt", "ok", message_id, "回执到达")
    bus.publish({"type": "confirmed", "message_id": message_id, "at": now_iso()})
    return updated


# ------------------------------------------------------------------ 演示辅助

def seed_demo(count: int = 5) -> list[dict]:
    """一次性灌几条历史消息，省得一打开页面是空的。"""
    platforms = ["feishu", "dingtalk"]
    created = []
    for i in range(count):
        platform = platforms[i % len(platforms)]
        payload = mock_feed.make_event(platform)
        result = receive(platform, payload, {}, preparsed=True)
        if result["result"] == "accepted":
            created.append(result["message_id"])
    return created


def state_snapshot() -> dict:
    return {
        "mode": config.MODE,
        "stats": store.stats(),
        "platforms": [
            {"name": name, "label": config.PLATFORM_LABEL[name], "color": config.PLATFORM_COLOR[name], "ready": True}
            for name in ADAPTERS
        ],
        "status_flow": state_machine.describe(),
        "subscribers": bus.subscriber_count(),
    }
