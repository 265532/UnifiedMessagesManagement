"""钉钉长连接（Stream 模式）通道的单元测试。

只覆盖不碰网络的部分：前置检查、消息进统一入口、字段映射、幂等、状态快照。
真实连网关必须要企业应用的 ClientID/ClientSecret，那属于联调，不放在单测里跑。
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from adapters.dingtalk import DingTalkAdapter  # noqa: E402
from adapters.dingtalk_stream import DingTalkStreamRunner  # noqa: E402
from core import service, store  # noqa: E402

# 一条钉钉机器人消息的真实字段结构（群聊里 @机器人 之后钉钉推下来的样子）
PAYLOAD = {
    "msgId": "msg-001",
    "senderNick": "姚锋",
    "senderId": "uid-001",
    "conversationId": "cid-dingtalk-group",
    "conversationTitle": "欢迎试用钉钉群",
    "conversationType": "2",
    "msgtype": "text",
    "text": {"content": "接口超时了，帮忙看下"},
    "createAt": 1763000000000,
    "isInAtList": True,
    "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
}


class DingTalkStreamTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db_path = config.DB_PATH
        self._orig_mode = config.MODE
        self._orig_dingtalk = dict(config.DINGTALK)

        config.DB_PATH = os.path.join(self._tmp.name, "test.db")
        store.init_db()
        self.runner = DingTalkStreamRunner()

    def tearDown(self):
        config.DB_PATH = self._orig_db_path
        config.MODE = self._orig_mode
        config.DINGTALK.clear()
        config.DINGTALK.update(self._orig_dingtalk)
        self._tmp.cleanup()

    # ---------------------------------------------------------- 前置检查
    def test_missing_reason_without_credentials(self):
        """没填 ClientID/Secret 时要明确指出缺什么，别让人猜。"""
        config.DINGTALK["app_key"] = ""
        config.DINGTALK["app_secret"] = ""
        reason = self.runner.missing_reason()
        self.assertIn("DINGTALK_APP_KEY", reason)

    def test_missing_reason_with_credentials(self):
        """凭证齐了、依赖也装了，就应当返回空字符串。

        dingtalk-stream 是可选依赖，不装也能跑整套单测。这里用 mock 伪造一个
        已安装的模块，让这个用例只验证「凭证齐全」这一段判断，不受本机是否
        真的装了 SDK 影响——否则没装的环境里会误报失败。
        """
        config.DINGTALK["app_key"] = "fake-client-id"
        config.DINGTALK["app_secret"] = "fake-client-secret"
        with mock.patch.dict(sys.modules, {"dingtalk_stream": mock.MagicMock()}):
            self.assertEqual("", self.runner.missing_reason())

    def test_start_refuses_without_credentials(self):
        """缺凭证时 start 不能硬起线程，要返回 False 并留下原因。"""
        config.DINGTALK["app_key"] = ""
        config.DINGTALK["app_secret"] = ""
        self.assertFalse(self.runner.start())
        self.assertIn("DINGTALK_APP_KEY", self.runner.last_error)

    # ---------------------------------------------------------- 验签分支
    def test_webhook_channel_still_requires_signature(self):
        """真实模式下走 HTTP 回调入口，没有签名就必须拒掉。"""
        config.MODE = "real"
        config.DINGTALK["app_secret"] = ""  # 没有密钥，签名不可能验过
        with self.assertRaises(service.ReceiveError) as ctx:
            service.receive("dingtalk", PAYLOAD, {}, trusted=False)
        self.assertEqual("verify", ctx.exception.stage)

    def test_trusted_channel_skips_http_signature(self):
        """长连接通道不传 timestamp/sign，但身份已在建连时验过，应当放行。"""
        config.MODE = "real"
        config.DINGTALK["app_secret"] = ""
        result = service.receive("dingtalk", PAYLOAD, {}, trusted=True)
        self.assertEqual("accepted", result["result"])
        self.assertEqual("stored", result["status"])

    # ---------------------------------------------------------- 字段映射
    def test_payload_fields_map_to_standard_message(self):
        """钉钉的字段名和我们的标准格式差得远，映射不能错。"""
        msg = DingTalkAdapter().parse(PAYLOAD)
        self.assertEqual("dingtalk", msg["platform"])
        self.assertEqual("msg-001", msg["event_id"])
        self.assertEqual("姚锋", msg["sender"]["name"])
        self.assertEqual("uid-001", msg["sender"]["id"])
        self.assertEqual("欢迎试用钉钉群", msg["conversation"]["name"])
        self.assertEqual("cid-dingtalk-group", msg["conversation"]["id"])
        self.assertEqual("text", msg["msg_type"])
        self.assertEqual("接口超时了，帮忙看下", msg["content"]["text"])

    # ---------------------------------------------------------- 幂等
    def test_same_msg_id_received_twice_is_dropped(self):
        """钉钉断线重连可能把同一条消息推两次，靠 msgId 去重。"""
        first = service.receive("dingtalk", PAYLOAD, {}, trusted=True)
        second = service.receive("dingtalk", PAYLOAD, {}, trusted=True)
        self.assertEqual("accepted", first["result"])
        self.assertEqual("duplicate", second["result"])

    # ---------------------------------------------------------- 入口与状态
    def test_handle_payload_goes_through_unified_entry(self):
        """长连接收到消息后走的就是 service.receive，状态要能一路推到已入库。"""
        self.runner._handle_payload(PAYLOAD)
        self.assertEqual(1, self.runner.received_count)
        self.assertTrue(self.runner.last_message_at)

        messages = store.list_messages(platform="dingtalk", limit=5)
        self.assertEqual(1, len(messages))
        self.assertEqual("stored", messages[0]["status"])

    def test_status_snapshot_shape(self):
        """healthz 依赖这个结构，键名不能随手改。"""
        status = self.runner.status()
        for key in ("enabled", "running", "missing", "last_error",
                    "last_message_at", "received_count"):
            self.assertIn(key, status)
        self.assertFalse(status["running"])  # 没 start 过，不该是连接中


if __name__ == "__main__":
    unittest.main()
