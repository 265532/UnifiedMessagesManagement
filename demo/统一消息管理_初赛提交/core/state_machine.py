"""消息状态机。

一条消息从进来到确认，只能沿着 config.STATUS_FLOW 里的边走的。
非法跳转直接抛异常，不会悄悄把状态改掉。
"""

from config import STATUS_FLOW, STATUS_LABEL


class IllegalTransition(Exception):
    """出现了状态机不允许的流转。"""


def can_transition(current: str, target: str) -> bool:
    return target in STATUS_FLOW.get(current, [])


def check(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise IllegalTransition(
            f"状态 {STATUS_LABEL.get(current, current)} 不能直接变成 {STATUS_LABEL.get(target, target)}"
        )


def next_states(current: str) -> list[str]:
    return STATUS_FLOW.get(current, [])


def describe() -> dict:
    """给前端画状态机图用。"""
    return {
        "flow": STATUS_FLOW,
        "labels": STATUS_LABEL,
    }


def is_terminal(state: str) -> bool:
    return len(STATUS_FLOW.get(state, [])) == 0
