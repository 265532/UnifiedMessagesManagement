"""模拟平台事件源。

演示时没有真实企业账号，用它按节奏往系统里灌消息，让闭环能完整跑一遍。
真实接入后这个模块不参与，adapter 直接收平台回调就行。
"""

import random
import time
import uuid

from core.schema import make_message

# 演示用的对话和人物，做成两组，看起来像真的两个平台在同时推消息
_SCENES = {
    "feishu": {
        "conversations": [
            {"id": "oc_feishu_dev", "name": "产品研发组"},
            {"id": "oc_feishu_weekly", "name": "周会同步"},
        ],
        "senders": [
            {"id": "ou_zhang", "name": "张颖"},
            {"id": "ou_li", "name": "李工"},
        ],
        "texts": [
            "登录页的接口联调好了，你那边什么时候能用？",
            "这版设计稿我改了三处，主要动了消息卡片的间距。",
            "初赛文档我这周五写完，需要谁帮忙看一下格式？",
            "飞书的回调地址已经配好，测试环境能收到事件了。",
            "明天上午十点评审，材料发群里了。",
        ],
    },
    "dingtalk": {
        "conversations": [
            {"id": "cid_ding_ops", "name": "运维值班"},
            {"id": "cid_ding_test", "name": "测试反馈"},
        ],
        "senders": [
            {"id": "dt_wang", "name": "王磊"},
            {"id": "dt_chen", "name": "陈晨"},
        ],
        "texts": [
            "线上那条告警我处理了，是 token 过期导致的。",
            "压测结果出来了，50 并发下 P95 大概 1.2 秒。",
            "钉钉这边的审批流要单独申请权限，得等两天。",
            "文件我传到共享盘了，路径发你钉钉。",
            "这个月的迭代计划更新了，注意查收。",
        ],
    },
}


def make_event(platform: str, repeat: bool = False) -> dict:
    """生成一条标准消息。

    repeat=True 时复用上一条事件的 event_id 之外的部分，用来演示幂等去重：
    系统会认出这是重复事件，直接丢弃，不会产生第二条消息。
    """
    scene = _SCENES[platform]
    conversation = random.choice(scene["conversations"])
    sender = random.choice(scene["senders"])
    text = random.choice(scene["texts"])

    event_id = f"evt_{uuid.uuid4().hex[:16]}"

    content: dict = {"text": text}
    msg_type = "text"

    # 每五六条里插一条文件消息，界面上能看到两种类型都支持
    if random.random() < 0.18:
        msg_type = "file"
        content = {"file_name": random.choice(["需求分析v1.1.docx", "接口契约.xlsx", "压测报告.pdf"])}

    return make_message(
        platform=platform,
        event_id=event_id,
        conversation=conversation,
        sender=sender,
        msg_type=msg_type,
        content=content,
    )


def make_duplicate(platform: str, message: dict) -> dict:
    """造一条和已有消息 event_id 相同的事件，用来验证去重。"""
    dup = dict(message)
    dup["id"] = uuid.uuid4().hex
    dup["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    dup["updated_at"] = dup["created_at"]
    return dup
