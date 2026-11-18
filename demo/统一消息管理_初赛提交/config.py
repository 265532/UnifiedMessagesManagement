"""统一配置。

所有可变项集中在这里。演示时不需要改代码，改环境变量或 .env 文件即可。
"""

import os


def _load_dotenv() -> None:
    """把项目根目录的 .env 读进环境变量。

    没引第三方库（python-dotenv），因为格式就 key=value 一种，十几行的事。
    已经存在于环境变量里的值不覆盖，方便临时用命令行参数压过 .env。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# ---------------------------------------------------------------- 运行模式

# 演示模式：用内置的模拟平台推送消息，不依赖任何真实凭证，闭环照样能跑通。
# 接真平台时把 AUTO_PLATFORM_MODE 设为 "real"，并在下面填好凭证。
MODE = os.getenv("UMM_MODE", "mock")

# mock 模式下，每隔多少秒模拟一条平台事件进来
MOCK_INTERVAL_SECONDS = int(os.getenv("UMM_MOCK_INTERVAL", "6"))


# ---------------------------------------------------------------- 平台凭证
# 留空就是 mock；填了且 MODE=real 时，adapter 会走真实 API。

FEISHU = {
    "app_id": os.getenv("FEISHU_APP_ID", ""),
    "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
    "verification_token": os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
    "encrypt_key": os.getenv("FEISHU_ENCRYPT_KEY", ""),
    # 群自定义机器人的 Webhook 地址。填了之后发送方向直接走它，不需要 App ID/Secret，
    # 也不受应用调用权限限制；留空则走「应用身份 + tenant_access_token」那套。
    "webhook_url": os.getenv("FEISHU_WEBHOOK_URL", ""),
    "base_url": "https://open.feishu.cn/open-apis",
}

DINGTALK = {
    "app_key": os.getenv("DINGTALK_APP_KEY", ""),
    "app_secret": os.getenv("DINGTALK_APP_SECRET", ""),
    "robot_code": os.getenv("DINGTALK_ROBOT_CODE", ""),
    # 群自定义机器人的 Webhook（形如 https://oapi.dingtalk.com/robot/send?access_token=xxx）。
    # 填了之后发送方向直接走它，不需要 app_key / app_secret；留空则走自建应用那套。
    "webhook_url": os.getenv("DINGTALK_WEBHOOK_URL", ""),
    # 机器人安全设置里勾了「加签」时填这串（SEC 开头、67 位）。选「自定义关键词」或「IP 地址段」就不用填。
    "webhook_secret": os.getenv("DINGTALK_WEBHOOK_SECRET", ""),
    # 单聊回复的收件人 userId，取自企业内部应用通讯录。
    # 注意别拿回调里的 senderId 填这里：那个字段是钉钉加密过的（$:LWCP_v1:$...），
    # 调发送接口会报无效人员。填了之后网页回复走机器人单聊，手机上直接收到。
    "default_user_id": os.getenv("DINGTALK_DEFAULT_USER_ID", ""),
    "base_url": "https://oapi.dingtalk.com",
    # 新版服务端 API 的域名。机器人单聊、Stream 网关都走这个域，和上面那个不是一套。
    "api_base_url": "https://api.dingtalk.com",
}

# 钉钉长连接（Stream 模式）。打开后 app.py 启动时会另起一条 WebSocket 连钉钉网关，
# 真实消息从这条连接进来，不需要公网 IP、不用开端口。
# 前提：上面 DINGTALK 里填了 app_key / app_secret，且开放平台那个应用开了机器人能力、
# 并把消息接收方式选成 Stream 模式。
# 默认关闭。关着的时候这条通道完全不碰：不连网、不导入 SDK，少装依赖也不影响其他功能。
DINGTALK_STREAM_ENABLED = os.getenv("UMM_DINGTALK_STREAM", "0") == "1"

WECOM = {
    "corp_id": os.getenv("WECOM_CORP_ID", ""),
    "corp_secret": os.getenv("WECOM_CORP_SECRET", ""),
    "base_url": "https://qyapi.weixin.qq.com/cgi-bin",
}


# ---------------------------------------------------------------- 存储与网络

# 演示用 SQLite，单文件，零依赖。换 MySQL 时只改 core/store.py 一处。
DB_PATH = os.getenv("UMM_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "umm.db"))

HOST = os.getenv("UMM_HOST", "127.0.0.1")
PORT = int(os.getenv("UMM_PORT", "8000"))

# 统一入口登录口令。演示模式给个简单的，生产换成数据库校验。
DEMO_USER = os.getenv("UMM_USER", "demo")
DEMO_PASSWORD = os.getenv("UMM_PASSWORD", "demo1234")
SESSION_TIMEOUT_MINUTES = 30


# ---------------------------------------------------------------- 业务参数

# Token 剩余有效期低于这个秒数就主动刷新（对应 NFR-02）
TOKEN_REFRESH_THRESHOLD = 300

# 429 限流退避：0.5s 起步，指数增长，最多重试 5 次（对应 NFR-01）
RETRY_BASE_DELAY = 0.5
RETRY_MAX_TIMES = 5

# 平台回调允许的时间偏差（秒）。超过这个值直接拒，防止有人把抓到的旧请求反复重放。
CALLBACK_MAX_SKEW_SECONDS = 3600

# 消息状态机允许的流转（core/state_machine.py 会读它做校验）
STATUS_FLOW = {
    "received": ["stored", "parse_failed", "ignored"],
    "parse_failed": ["stored", "dead"],
    "stored": ["displayed"],
    "displayed": ["processed"],
    "processed": ["replying"],
    "replying": ["replied", "send_failed"],
    "send_failed": ["replying", "dead"],
    "replied": ["confirmed"],
    "confirmed": [],
    "ignored": [],
    "dead": [],
}

# 界面上的中文状态名
STATUS_LABEL = {
    "received": "已接收",
    "parse_failed": "解析失败",
    "stored": "已入库",
    "displayed": "已展示",
    "processed": "已处理",
    "replying": "回复中",
    "replied": "已发送",
    "send_failed": "发送失败",
    "confirmed": "已确认",
    "ignored": "已忽略",
    "dead": "已归档",
}

PLATFORM_LABEL = {
    "feishu": "飞书",
    "dingtalk": "钉钉",
    "wecom": "企业微信",
}

PLATFORM_COLOR = {
    "feishu": "#3370ff",
    "dingtalk": "#1a9df0",
    "wecom": "#07c160",
}
