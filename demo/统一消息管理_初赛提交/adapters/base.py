"""平台适配器抽象接口。

核心服务只认这个接口。新增一个平台时，写一个子类就够，不用碰 core 里的任何代码。

三个必须实现的方法：
    verify  验签，判断这次回调是不是平台真发来的
    parse   把平台消息体转成内部标准消息
    send    把回复发到平台，返回发送结果
"""

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    name: str = ""
    display_name: str = ""

    @abstractmethod
    def verify(self, payload: dict, headers: dict) -> bool:
        """校验回调来源。模拟模式下直接返回 True。"""

    @abstractmethod
    def parse(self, payload: dict) -> dict:
        """平台事件 → 标准消息 dict。字段见 core/schema.py。"""

    @abstractmethod
    def send(self, conversation_id: str, msg_type: str, content: dict) -> dict:
        """发送一条消息。返回 {"ok": bool, "platform_msg_id": str, "error": str}。

        只做单次调用。限流重试、Token 刷新这些统一放在 core/service.py 处理，
        否则每加一个平台就要重写一遍重试逻辑。
        """
