"""状态机测试：合法边能走、非法边被挡住、终态不会被当成中间态。

跑法：在项目根执行 `python -m unittest discover -s tests -v`
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import state_machine  # noqa: E402


class StateMachineTest(unittest.TestCase):
    def test_normal_path_is_walkable(self):
        """一条消息从进来到确认，这条主干上的每一跳都必须放行。"""
        path = ["received", "stored", "displayed", "processed", "replying", "replied", "confirmed"]
        for current, target in zip(path, path[1:]):
            with self.subTest(edge=f"{current} -> {target}"):
                self.assertTrue(state_machine.can_transition(current, target))

    def test_skipping_a_step_is_rejected(self):
        """最常见的误用：还没展示就回复。这种跳步必须挡住。"""
        self.assertFalse(state_machine.can_transition("stored", "replied"))
        with self.assertRaises(state_machine.IllegalTransition):
            state_machine.check("stored", "replied")

    def test_retry_loop_is_allowed(self):
        """发送失败后可以重试，重试再失败才进死信，这个环是设计内的。"""
        self.assertTrue(state_machine.can_transition("replying", "send_failed"))
        self.assertTrue(state_machine.can_transition("send_failed", "replying"))
        self.assertTrue(state_machine.can_transition("send_failed", "dead"))

    def test_backwards_is_rejected(self):
        """往回退（replied 退回 processed）不允许，否则重试计数和审计都会乱。"""
        self.assertFalse(state_machine.can_transition("replied", "processed"))
        self.assertFalse(state_machine.can_transition("confirmed", "replied"))

    def test_terminal_states(self):
        for state in ("confirmed", "dead", "ignored"):
            with self.subTest(state=state):
                self.assertTrue(state_machine.is_terminal(state))
        for state in ("processed", "replying", "send_failed"):
            with self.subTest(state=state):
                self.assertFalse(state_machine.is_terminal(state))

    def test_unknown_state_has_no_way_out(self):
        self.assertEqual(state_machine.next_states("not_a_state"), [])
        self.assertFalse(state_machine.can_transition("not_a_state", "stored"))

    def test_describe_exposes_flow_and_labels(self):
        """前端画状态机图靠这个，两个键都不能缺。"""
        data = state_machine.describe()
        self.assertIn("flow", data)
        self.assertIn("labels", data)
        self.assertEqual(set(data["flow"]), set(data["labels"]))


if __name__ == "__main__":
    unittest.main()
