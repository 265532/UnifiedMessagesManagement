"""持久化测试：幂等去重、状态推进、乐观锁。

每个用例都换一个临时 SQLite 文件，不碰 data/umm.db，跑完就删。
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import state_machine, store  # noqa: E402
from core.schema import make_message  # noqa: E402


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db_path = config.DB_PATH
        config.DB_PATH = os.path.join(self._tmp.name, "test.db")
        store.init_db()

    def tearDown(self):
        config.DB_PATH = self._orig_db_path
        self._tmp.cleanup()

    @staticmethod
    def _message(event_id: str = "evt-1") -> dict:
        return make_message(
            platform="dingtalk",
            event_id=event_id,
            conversation={"id": "cid-1", "name": "运维值班"},
            sender={"id": "uid-1", "name": "姚锋"},
            msg_type="text",
            content={"text": "压测结果出来了"},
        )

    def test_insert_then_read_back(self):
        msg = self._message()
        self.assertTrue(store.insert_message(msg))

        loaded = store.get_message(msg["id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["status"], "received")
        self.assertEqual(loaded["content"]["text"], "压测结果出来了")

    def test_same_event_id_is_rejected(self):
        """平台重复投递：第二次必须返回 False，库里还是一条。"""
        self.assertTrue(store.insert_message(self._message("evt-dup")))
        self.assertFalse(store.insert_message(self._message("evt-dup")))
        self.assertEqual(store.stats()["total"], 1)

    def test_log_duplicate_records_trace_and_count(self):
        msg = self._message("evt-dup2")
        store.insert_message(msg)
        self.assertTrue(store.log_duplicate("evt-dup2"))
        self.assertEqual(store.stats()["rejected_duplicates"], 1)
        # 不存在的 event_id 不该凭空造出记录
        self.assertFalse(store.log_duplicate("evt-not-exist"))

    def test_transition_advances_and_writes_trace(self):
        msg = self._message()
        store.insert_message(msg)
        updated = store.transition(msg["id"], "stored", note="入库")
        self.assertEqual(updated["status"], "stored")
        self.assertEqual(updated["version"], 2)

        traces = store.get_traces(msg["id"])
        self.assertEqual([t["status"] for t in traces], ["received", "stored"])

    def test_illegal_transition_is_blocked(self):
        msg = self._message()
        store.insert_message(msg)
        with self.assertRaises(state_machine.IllegalTransition):
            store.transition(msg["id"], "replied")

    def test_optimistic_lock_rejects_stale_version(self):
        msg = self._message()
        store.insert_message(msg)
        store.transition(msg["id"], "stored")
        with self.assertRaises(RuntimeError):
            store.transition(msg["id"], "displayed", expected_version=1)

    def test_optimistic_lock_accepts_current_version(self):
        msg = self._message()
        store.insert_message(msg)
        store.transition(msg["id"], "stored")
        updated = store.transition(msg["id"], "displayed", expected_version=2)
        self.assertEqual(updated["status"], "displayed")

    def test_transition_on_missing_message_raises(self):
        with self.assertRaises(KeyError):
            store.transition("no-such-id", "stored")

    def test_stats_counts_by_platform_and_status(self):
        store.insert_message(self._message("evt-a"))
        store.insert_message(make_message(
            platform="feishu",
            event_id="evt-b",
            conversation={"id": "cid-2", "name": "产品群"},
            sender={"id": "uid-2", "name": "张颖"},
            msg_type="text",
            content={"text": "迭代计划更新了"},
        ))
        data = store.stats()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["by_platform"], {"dingtalk": 1, "feishu": 1})
        self.assertEqual(data["by_status"], {"received": 2})

    def test_reset_demo_data_clears_everything(self):
        store.insert_message(self._message())
        store.reset_demo_data()
        self.assertEqual(store.stats()["total"], 0)


if __name__ == "__main__":
    unittest.main()
