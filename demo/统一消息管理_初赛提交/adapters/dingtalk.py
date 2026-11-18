"""钉钉适配器。

发送方向有三条通道，按这个顺序判断：
    1. DINGTALK_WEBHOOK_URL 有值 → 群自定义机器人 Webhook，不需要 access_token
    2. UMM_MODE=mock           → 假装发成功，用来演示闭环
    3. UMM_MODE=real           → 工作通知接口，app_key + app_secret 换 access_token

第 3 条要建自建应用并申请权限；只做发送演示的话第 1 条最省事，
在群里加个自定义机器人拿到 Webhook 就能用。
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config
from adapters.base import PlatformAdapter
from core.schema import make_message


def _header(headers, name: str, default: str = "") -> str:
    """从 header 里取一个键，大小写不敏感。

    Flask 传进来的是 EnvironHeaders，测试里可能直接给一个 dict，
    两种都要能取到，所以统一走遍历，不依赖某一个实现的 get。
    """
    if headers is None:
        return default
    for key, value in dict(headers).items():
        if str(key).lower() == name.lower():
            return str(value)
    return default


class DingTalkAdapter(PlatformAdapter):
    name = "dingtalk"
    display_name = "钉钉"

    def __init__(self) -> None:
        # 旧版 oapi.dingtalk.com 的 token
        self._token = ""
        self._token_expire_at = 0.0
        # 新版 api.dingtalk.com 的 token。两套 token 不通用，各存一份
        self._app_token = ""
        self._app_token_expire_at = 0.0

    def verify(self, payload: dict, headers: dict) -> bool:
        """校验钉钉回调的签名。

        钉钉在回调请求的 header 里带 timestamp（毫秒）和 sign，
        sign = base64(HMAC-SHA256(key=app_secret, msg=timestamp))。
        除了比对签名，还要卡时间偏差，否则抓到的旧请求可以被无限重放。
        """
        if config.MODE == "mock":
            return True

        secret = config.DINGTALK.get("app_secret", "")
        timestamp = _header(headers, "timestamp")
        sign = _header(headers, "sign")

        # 没配 app_secret 就没有可比对的密钥。这时候宁可拒掉整个回调入口，
        # 也不能放行——否则谁构造一个 json 都能往库里写消息。
        if not (secret and timestamp and sign):
            return False

        try:
            ts_ms = int(float(timestamp))
        except (TypeError, ValueError):
            return False

        if abs(time.time() * 1000 - ts_ms) > config.CALLBACK_MAX_SKEW_SECONDS * 1000:
            return False

        expected = base64.b64encode(
            hmac.new(secret.encode("utf-8"), str(ts_ms).encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, sign)

    def parse(self, payload: dict) -> dict:
        """钉钉机器人回调格式。"""
        sender_nick = payload.get("senderNick", "钉钉用户")
        sender_id = payload.get("senderId", "unknown")
        conversation_id = payload.get("conversationId", "")
        conversation_title = payload.get("conversationTitle") or ""
        if not conversation_title:
            # 单聊会话钉钉不给标题。直接拿 conversationId 当名字，界面上就是
            # 一长串 cid4WvgKz… 的加密字符串，看不出这条是谁发的。
            # 单聊对面就是发消息这个人，用昵称更直观。
            conversation_title = sender_nick if str(payload.get("conversationType", "")) == "1" else conversation_id

        text = payload.get("text", {}).get("content", "")
        msg_type = "text" if text else "file"

        return make_message(
            platform=self.name,
            event_id=payload.get("msgId", ""),
            conversation={"id": conversation_id, "name": conversation_title},
            sender={"id": sender_id, "name": sender_nick},
            msg_type=msg_type,
            content={"text": text} if msg_type == "text" else {
                "file_name": payload.get("fileName", "未命名文件"),
            },
        )

    def send(self, conversation_id: str, msg_type: str, content: dict) -> dict:
        # 通道一：机器人单聊。配了收件人 userId 就先走这条——它才是真正意义上的
        # 「原路返回」：消息回到那个人和机器人的会话里，而不是灌进某个群。
        single_error = ""
        receiver = config.DINGTALK.get("default_user_id", "")
        if receiver and msg_type == "text":
            result = self._send_by_robot_single(receiver, content.get("text", ""))
            if result.get("ok"):
                return result
            # 单聊没发出去就继续往下试，别让一条消息卡死整条回复链
            single_error = result.get("error", "")

        webhook = config.DINGTALK.get("webhook_url", "")
        if webhook:
            # 配了群机器人 Webhook 就从这条通道发。它不需要 access_token，
            # 所以 mock 模式下也照样真发——演示时"消息真的进了钉钉群"。
            return self._send_by_webhook(webhook, msg_type, content)

        if single_error:
            # 单聊通道试过了、确实发不出去，也没有群 Webhook 兜底。
            # 退回工作通知没意义——收件人不是同一个人，直接把真实原因报出去。
            return {"ok": False, "platform_msg_id": "", "error": single_error}

        if config.MODE == "mock":
            time.sleep(0.2)
            return {"ok": True, "platform_msg_id": f"dt_mock_{int(time.time() * 1000)}", "error": ""}

        token = self._get_token()
        if not token:
            return {"ok": False, "platform_msg_id": "", "error": "获取钉钉 access_token 失败"}

        body = {
            "agent_id": config.DINGTALK.get("robot_code", ""),
            "msg": {
                "msgtype": "text" if msg_type == "text" else "file",
                "text": {"content": content.get("text", "")} if msg_type == "text" else None,
            },
        }
        result = self._post_json(
            f"{config.DINGTALK['base_url']}/topapi/message/corpconversation/asyncsend_v2?access_token={token}",
            body,
        )
        if result.get("errcode") == 0:
            return {"ok": True, "platform_msg_id": str(result.get("task_id", "")), "error": ""}
        return {"ok": False, "platform_msg_id": "", "error": result.get("errmsg", "钉钉返回未知错误")}

    def _send_by_robot_single(self, user_id: str, text: str) -> dict:
        """机器人单聊：把消息发到某个人与机器人的会话里。

        和群 Webhook 的区别是它认应用身份：先用 app_key/app_secret 换新版
        access_token，再把 token 放在 x-acs-dingtalk-access-token 头上。
        msgKey=sampleText 是钉钉给纯文本定好的模板名，换成别的会报参数错误。
        """
        token = self._get_app_token()
        if not token:
            return {"ok": False, "platform_msg_id": "", "error": "获取新版 access_token 失败"}

        payload = {
            "robotCode": config.DINGTALK["app_key"],
            "userIds": [user_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        result = self._post_json(
            f"{config.DINGTALK['api_base_url']}/v1.0/robot/oToMessages/batchSend",
            payload,
            {"x-acs-dingtalk-access-token": token},
        )

        key = result.get("processQueryKey", "")
        if key:
            return {"ok": True, "platform_msg_id": key, "error": ""}
        if result.get("invalidStaffIdList"):
            return {"ok": False, "platform_msg_id": "", "error": "收件人 userId 无效，检查 DINGTALK_DEFAULT_USER_ID"}
        return {
            "ok": False,
            "platform_msg_id": "",
            "error": result.get("message") or f"钉钉返回 {result}",
        }

    def _send_by_webhook(self, url: str, msg_type: str, content: dict) -> dict:
        """群自定义机器人通道：POST 一个 json 就到群里，不需要 access_token。"""
        if msg_type != "text":
            return {
                "ok": False,
                "platform_msg_id": "",
                "error": "群机器人 Webhook 只能发文本；发文件要走自建应用上传素材拿 media_id",
            }

        payload = {"msgtype": "text", "text": {"content": content.get("text", "")}}
        result = self._post_json(self._sign_url(url), payload)

        if result.get("errcode") == 0:
            return {"ok": True, "platform_msg_id": "", "error": ""}
        return {
            "ok": False,
            "platform_msg_id": "",
            "error": result.get("errmsg") or f"Webhook 返回 {result}",
        }

    @staticmethod
    def _sign_url(url: str) -> str:
        """安全设置勾了「加签」时，把 timestamp 和 sign 拼到 URL 上；没配 secret 就原样返回。"""
        secret = config.DINGTALK.get("webhook_secret", "")
        if not secret:
            return url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        joiner = "&" if "?" in url else "?"
        return f"{url}{joiner}timestamp={timestamp}&sign={sign}"

    def _get_app_token(self) -> str:
        """新版 access_token，给 api.dingtalk.com 那套接口用。

        和旧版 gettoken 不是一回事：域名不同、token 不通用，所以单独缓存一份，
        否则每次发单聊都要多打一次网络请求。
        """
        if self._app_token and time.time() < self._app_token_expire_at - config.TOKEN_REFRESH_THRESHOLD:
            return self._app_token

        result = self._post_json(
            f"{config.DINGTALK['api_base_url']}/v1.0/oauth2/accessToken",
            {"appKey": config.DINGTALK["app_key"], "appSecret": config.DINGTALK["app_secret"]},
        )
        token = result.get("accessToken", "")
        if token:
            self._app_token = token
            self._app_token_expire_at = time.time() + int(result.get("expireIn", 7200))
            return token
        return ""

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - config.TOKEN_REFRESH_THRESHOLD:
            return self._token

        query = urllib.parse.urlencode({
            "appkey": config.DINGTALK["app_key"],
            "appsecret": config.DINGTALK["app_secret"],
        })
        try:
            with urllib.request.urlopen(f"{config.DINGTALK['base_url']}/gettoken?{query}", timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError):
            return ""

        if result.get("errcode") == 0:
            self._token = result.get("access_token", "")
            self._token_expire_at = time.time() + int(result.get("expires_in", 7200))
            return self._token
        return ""

    @staticmethod
    def _post_json(url: str, body: dict, headers: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"errcode": e.code, "errmsg": f"HTTP {e.code}"}
        except urllib.error.URLError as e:
            return {"errcode": -1, "errmsg": f"网络错误: {e.reason}"}
