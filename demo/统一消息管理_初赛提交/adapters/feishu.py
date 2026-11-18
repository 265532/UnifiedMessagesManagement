"""飞书适配器。

发送方向有三条通道，按这个顺序判断：
    1. FEISHU_WEBHOOK_URL 有值 → 群自定义机器人 Webhook，不需要 token，也不受应用权限限制
    2. UMM_MODE=mock          → 假装发成功，用来演示闭环
    3. UMM_MODE=real          → 应用身份，tenant_access_token + 发送消息接口

第 3 条需要 FEISHU_APP_ID / FEISHU_APP_SECRET。自建应用被租户策略拒绝（返回 21001）时，
第 1 条是可用的替代，细节见 docs/飞书接入指南.md。
"""

import json
import time
import urllib.error
import urllib.request

import config
from adapters.base import PlatformAdapter
from core.schema import make_message


class FeishuAdapter(PlatformAdapter):
    name = "feishu"
    display_name = "飞书"

    def __init__(self) -> None:
        self._token = ""
        self._token_expire_at = 0.0

    # ------------------------------------------------------------ 验签
    def verify(self, payload: dict, headers: dict) -> bool:
        if config.MODE == "mock":
            return True

        token = config.FEISHU["verification_token"]
        if not token:
            # 真实模式却没配 Verification Token，等于任何人都能往这个回调口推消息，一律拒绝。
            # 飞书保存回调地址时发的 url_verification 不经过这里，所以不会影响地址配置。
            return False

        received = payload.get("header", {}).get("token") or payload.get("token")
        return received == token

    # ------------------------------------------------------------ 解析
    def parse(self, payload: dict) -> dict:
        """飞书事件格式：{"schema":"2.0","header":{...},"event":{...}}，这里只处理消息事件。"""
        header = payload.get("header", {})
        event = payload.get("event", payload)
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "unknown")
        content_text = message.get("content", "{}")

        try:
            content = json.loads(content_text) if isinstance(content_text, str) else content_text
        except json.JSONDecodeError:
            content = {"text": str(content_text)}

        msg_type = "text" if message.get("msg_type", "text") == "text" else "file"

        # event_id 在 v2 事件里挂在 header 上，老格式挂在 event 上，都兜一遍；
        # 它是幂等键，取错会导致重复消息拦不住
        event_id = (
            header.get("event_id")
            or event.get("event_id")
            or message.get("message_id", "")
        )

        return make_message(
            platform=self.name,
            event_id=event_id,
            conversation={
                "id": message.get("chat_id", ""),
                "name": message.get("chat_id", "未知会话"),
            },
            sender={"id": sender_id, "name": sender.get("sender_type", "飞书用户")},
            msg_type=msg_type,
            content={"text": content.get("text", "")} if msg_type == "text" else {
                "file_name": content.get("file_name", "未命名文件"),
                "file_key": content.get("file_key", ""),
            },
        )

    # ------------------------------------------------------------ 发送
    def send(self, conversation_id: str, msg_type: str, content: dict) -> dict:
        webhook = config.FEISHU.get("webhook_url", "")
        if webhook:
            # 配了群机器人 Webhook 就从这条通道发。它不需要拿 token，也不受自建应用
            # 调用权限的限制，所以 mock 模式下也照样真发——演示时"消息真的进了飞书群"。
            return self._send_by_webhook(webhook, msg_type, content)

        if config.MODE == "mock":
            time.sleep(0.25)  # 模拟网络耗时，让前端的状态流转看得见
            return {"ok": True, "platform_msg_id": f"om_mock_{int(time.time() * 1000)}", "error": ""}

        token = self._get_token()
        if not token:
            return {"ok": False, "platform_msg_id": "", "error": "获取 tenant_access_token 失败"}

        body = {
            "receive_id": conversation_id,
            "msg_type": msg_type if msg_type == "text" else "file",
            "content": json.dumps(content, ensure_ascii=False),
        }
        result = self._post(
            f"{config.FEISHU['base_url']}/im/v1/messages?receive_id_type=chat_id",
            body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        )

        if result.get("code") == 0:
            return {
                "ok": True,
                "platform_msg_id": result.get("data", {}).get("message_id", ""),
                "error": "",
            }
        return {"ok": False, "platform_msg_id": "", "error": result.get("msg", "飞书返回未知错误")}

    # ------------------------------------------------------------ 内部
    def _send_by_webhook(self, url: str, msg_type: str, content: dict) -> dict:
        """群自定义机器人通道：POST 一个 json 就到群里，不需要 token。"""
        if msg_type != "text":
            return {
                "ok": False,
                "platform_msg_id": "",
                "error": "群机器人 Webhook 只能发文本；发文件要先以应用身份上传素材拿 file_key",
            }

        payload = {"msg_type": "text", "content": {"text": content.get("text", "")}}
        result = self._post(url, payload)

        # 新版返回 {"code":0,"msg":"success"}，老版返回 {"StatusCode":0,"StatusMessage":"success"}
        code = result.get("code", result.get("StatusCode"))
        if code == 0:
            return {"ok": True, "platform_msg_id": "", "error": ""}
        return {
            "ok": False,
            "platform_msg_id": "",
            "error": result.get("msg") or result.get("StatusMessage") or f"Webhook 返回 {result}",
        }

    def _get_token(self) -> str:
        """带缓存的 token，剩余有效期不足阈值时主动刷新。"""
        if self._token and time.time() < self._token_expire_at - config.TOKEN_REFRESH_THRESHOLD:
            return self._token

        result = self._post(
            f"{config.FEISHU['base_url']}/auth/v3/tenant_access_token/internal",
            {"app_id": config.FEISHU["app_id"], "app_secret": config.FEISHU["app_secret"]},
        )
        if result.get("code") == 0:
            self._token = result.get("tenant_access_token", "")
            self._token_expire_at = time.time() + int(result.get("expire", 7200))
            return self._token
        return ""

    @staticmethod
    def _post(url: str, body: dict, headers: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers or {"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "ignore")
            return {"code": e.code, "msg": f"HTTP {e.code}: {body_text[:200]}"}
        except urllib.error.URLError as e:
            return {"code": -1, "msg": f"网络错误: {e.reason}"}
