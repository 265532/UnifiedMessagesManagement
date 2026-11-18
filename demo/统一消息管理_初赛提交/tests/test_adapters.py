"""适配器测试：验签和签名生成。

这两个地方都不发网络请求，纯算签名，所以可以放心在单测里跑。
真正发消息的路径用临时脚本打真接口验证过（见 docs 里的接入指南）。
"""

import base64
import hashlib
import hmac
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from adapters.dingtalk import DingTalkAdapter  # noqa: E402
from adapters.feishu import FeishuAdapter  # noqa: E402


def dingtalk_sign(secret: str, timestamp: str) -> str:
    """按钉钉文档的算法算一遍，用来对拍。"""
    digest = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class DingTalkVerifyTest(unittest.TestCase):
    def test_mock_mode_always_passes(self):
        with mock.patch.object(config, "MODE", "mock"):
            self.assertTrue(DingTalkAdapter().verify({}, {}))

    def test_real_mode_without_secret_rejects(self):
        """没有 app_secret 就没有可比对的密钥，必须拒，不能默认放行。"""
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": ""}, clear=False):
            self.assertFalse(DingTalkAdapter().verify({"text": {"content": "x"}}, {}))

    def test_real_mode_without_sign_rejects(self):
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": "s3cret"}, clear=False):
            self.assertFalse(DingTalkAdapter().verify({}, {"timestamp": str(int(time.time() * 1000))}))

    def test_correct_signature_passes(self):
        timestamp = str(int(time.time() * 1000))
        headers = {"timestamp": timestamp, "sign": dingtalk_sign("s3cret", timestamp)}
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": "s3cret"}, clear=False):
            self.assertTrue(DingTalkAdapter().verify({"text": {"content": "hi"}}, headers))

    def test_wrong_signature_rejects(self):
        timestamp = str(int(time.time() * 1000))
        headers = {"timestamp": timestamp, "sign": dingtalk_sign("wrong-secret", timestamp)}
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": "s3cret"}, clear=False):
            self.assertFalse(DingTalkAdapter().verify({"text": {"content": "hi"}}, headers))

    def test_stale_timestamp_rejects(self):
        """签名是对的，但时间戳太久远——抓包重放必须被挡。"""
        old = str(int((time.time() - 3 * 24 * 3600) * 1000))
        headers = {"timestamp": old, "sign": dingtalk_sign("s3cret", old)}
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": "s3cret"}, clear=False):
            self.assertFalse(DingTalkAdapter().verify({"text": {"content": "hi"}}, headers))

    def test_header_lookup_is_case_insensitive(self):
        """Flask 给的是 EnvironHeaders，测试里给 dict，两种都得取到。"""
        timestamp = str(int(time.time() * 1000))
        headers = {"Timestamp": timestamp, "SIGN": dingtalk_sign("s3cret", timestamp)}
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.DINGTALK, {"app_secret": "s3cret"}, clear=False):
            self.assertTrue(DingTalkAdapter().verify({"text": {"content": "hi"}}, headers))


class DingTalkSignUrlTest(unittest.TestCase):
    BASE = "https://oapi.dingtalk.com/robot/send?access_token=test-token"

    def test_no_secret_keeps_url_untouched(self):
        with mock.patch.dict(config.DINGTALK, {"webhook_secret": ""}, clear=False):
            self.assertEqual(DingTalkAdapter._sign_url(self.BASE), self.BASE)

    def test_secret_appends_timestamp_and_sign(self):
        with mock.patch.dict(config.DINGTALK, {"webhook_secret": "SECtest"}, clear=False):
            url = DingTalkAdapter._sign_url(self.BASE)
        self.assertIn("timestamp=", url)
        self.assertIn("sign=", url)
        self.assertTrue(url.startswith(self.BASE + "&"))
        # base64 里的 + / = 必须被 URL 编码，否则会被当成参数分隔符
        sign_part = url.split("sign=", 1)[1]
        self.assertNotIn("+", sign_part)
        self.assertNotIn("/", sign_part)


class FeishuVerifyTest(unittest.TestCase):
    def test_mock_mode_always_passes(self):
        with mock.patch.object(config, "MODE", "mock"):
            self.assertTrue(FeishuAdapter().verify({}, {}))

    def test_real_mode_without_token_rejects(self):
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.FEISHU, {"verification_token": ""}, clear=False):
            self.assertFalse(FeishuAdapter().verify({"header": {"token": "x"}}, {}))

    def test_matching_token_passes(self):
        """2.0 版本把 token 放在 header 里。"""
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.FEISHU, {"verification_token": "tok-123"}, clear=False):
            self.assertTrue(FeishuAdapter().verify({"header": {"token": "tok-123"}}, {}))

    def test_legacy_token_location_passes(self):
        """1.0 版本放在顶层，兼容。"""
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.FEISHU, {"verification_token": "tok-123"}, clear=False):
            self.assertTrue(FeishuAdapter().verify({"token": "tok-123"}, {}))

    def test_wrong_token_rejects(self):
        with mock.patch.object(config, "MODE", "real"), \
                mock.patch.dict(config.FEISHU, {"verification_token": "tok-123"}, clear=False):
            self.assertFalse(FeishuAdapter().verify({"header": {"token": "tok-456"}}, {}))


if __name__ == "__main__":
    unittest.main()
