"""内部标准消息格式。

各平台消息体长得不一样，进系统第一件事就是转成这个结构，后面所有代码只认这一套。
反向发消息时再由适配器转回平台格式。

字段改动要同步 docs/architecture.md 里的 Schema 表。
"""

import time
import uuid


def now_iso() -> str:
    """统一用本地时间字符串，方便前端直接显示，不用再转时区。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex


def make_message(
    platform: str,
    event_id: str,
    conversation: dict,
    sender: dict,
    msg_type: str,
    content: dict,
    reply_to: str | None = None,
) -> dict:
    """构造一条标准消息。

    event_id 是平台事件的唯一标识，用作幂等键：同一个事件重复投递只会入一条记录。
    """
    return {
        "id": new_id(),
        "platform": platform,
        "event_id": event_id,
        "conversation": conversation,
        "sender": sender,
        "msg_type": msg_type,
        "content": content,
        "reply_to": reply_to,
        "status": "received",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "version": 1,
    }


def validate(raw: dict) -> tuple[bool, str]:
    """接收前的格式校验。返回 (是否合法, 不合法原因)。

    校验不过的消息不会被直接丢掉，而是进 parse_failed 队列等人工处理。
    """
    required = ["platform", "event_id", "conversation", "sender", "msg_type", "content"]
    for field in required:
        if not raw.get(field):
            return False, f"缺少字段 {field}"

    if raw["platform"] not in ("feishu", "dingtalk", "wecom"):
        return False, f"未知平台 {raw['platform']}"

    if raw["msg_type"] not in ("text", "file", "todo"):
        return False, f"不支持的消息类型 {raw['msg_type']}"

    if raw["msg_type"] == "text" and not raw["content"].get("text"):
        return False, "文本消息内容为空"

    if raw["msg_type"] == "file" and not raw["content"].get("file_name"):
        return False, "文件消息缺少文件名"

    return True, ""


def summary(message: dict, max_len: int = 40) -> str:
    """给列表界面用的一行摘要。"""
    if message["msg_type"] == "text":
        text = message["content"].get("text", "").replace("\n", " ")
        return text[:max_len] + ("…" if len(text) > max_len else "")
    if message["msg_type"] == "file":
        return f"[文件] {message['content'].get('file_name', '')}"
    return f"[待办] {message['content'].get('title', '')}"
