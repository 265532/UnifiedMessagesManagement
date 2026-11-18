"""实时推送总线。

用的是 SSE（Server-Sent Events），不是 WebSocket。
原因很简单：Flask 开箱能跑 SSE，浏览器端就一个 EventSource，演示和部署都省事。
消息量不大，SSE 足够；真要做双向长连接再换 WebSocket。
"""

import queue
import threading

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    """每个浏览器标签页开一个队列，互不干扰。"""
    q: queue.Queue = queue.Queue(maxsize=200)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def publish(event: dict) -> None:
    """广播一条事件。队列满了就丢旧的，不能因为一个卡住的页面拖垮整个服务。"""
    with _lock:
        targets = list(_subscribers)

    for q in targets:
        try:
            q.put_nowait(event)
        except queue.Full:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except queue.Empty:
                pass


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)
