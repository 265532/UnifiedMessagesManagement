# 代码仓库与运行说明

> 项目名称：UnifiedMessagesManagement（多平台连接器与统一消息管理）
> 报名序号：47
> 队伍人员：队长廖俊健，队员姚峰
> 状态：仓库与设计运行说明；当前仓库尚无产品源码，不能声称干净环境启动成功。

## 1. 仓库信息

| 项目 | 内容 |
|---|---|
| 仓库地址 | `https://github.com/265532/UnifiedMessagesManagement.git` |
| 当前本地分支 | `harness/bootstrap` |
| 当前本地 HEAD | `0fb35d80f8b1aa316e27986422b826f0747b8ca7` |
| 评审提交 | 待产品代码提交后确认 |
| 公开可访问性 | 待从非作者环境复核 |
| 演示视频 | 暂无且不需要补录 |

## 2. 当前代码状态

当前仓库包含 Harness 工程、需求与设计文档、契约和静态原型；尚未包含统一消息产品后端、前端实现、平台 Adapter、数据库迁移或产品测试。因此当前 HEAD 不能作为“可运行产品初版”的评审提交。

## 3. 设计运行方式（待实现后验证）

以下为选型确定后的目标运行方式，尚未实际执行成功：

```bash
cp .env.example .env
# 由人工填入测试企业凭证，不提交真实密钥
docker compose up --build
```

目标服务：

| 服务 | 说明 |
|---|---|
| `web` | Vue 前端静态资源 |
| `api` | FastAPI REST、Webhook、WebSocket |
| `worker` | outbox 发送与补偿 |
| `mysql` | MySQL 8 |
| `redis` | Redis 7 |
| `nginx` | 前端托管与反向代理 |

目标健康检查：`GET /api/v1/health` 返回 `status=ok`。待产品代码补齐后，必须在干净 checkout 中执行启动、迁移、测试和健康检查，并记录命令、退出码和证据。

## 4. 不得提交的内容

不提交 `.env`、真实 Token、Cookie、平台密钥、个人聊天隐私、临时日志或无关大文件。截图与日志进入提交包前必须脱敏。