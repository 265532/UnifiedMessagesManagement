# 接口设计

> 项目名称：UnifiedMessagesManagement（多平台连接器与统一消息管理）
> 报名序号：47
> 队伍人员：队长廖俊健，队员姚峰
> 状态：接口设计稿；以 `contracts/openapi.json` 为准，不代表接口已实现。

## 1. 接口清单

| 序号 | 接口名称 | 接口路由 | 接口解释 |
|---:|---|---|---|
| 1 | 登录 | `POST /api/v1/auth/login` | 创建统一入口登录会话 |
| 2 | 退出登录 | `POST /api/v1/auth/logout` | 注销当前会话 |
| 3 | 当前用户 | `GET /api/v1/auth/me` | 获取当前登录用户与会话过期时间 |
| 4 | 消息列表 | `GET /api/v1/messages` | 按平台、会话、状态和游标查询消息 |
| 5 | 消息详情 | `GET /api/v1/messages/{messageId}` | 查询消息详情与状态历史 |
| 6 | 标记处理 | `POST /api/v1/messages/{messageId}/process` | 将消息标记为已处理 |
| 7 | 回复消息 | `POST /api/v1/messages/{messageId}/reply` | 受理文本或文件回复并进入发送队列 |
| 8 | 重试发送 | `POST /api/v1/messages/{messageId}/retry` | 对失败回复发起人工确认后的重试 |
| 9 | 待办列表 | `GET /api/v1/todos` | 查询跨平台待办事项 |
| 10 | 平台 Webhook | `POST /webhooks/{platform}` | 接收飞书或钉钉事件并完成验签受理 |
| 11 | 健康检查 | `GET /api/v1/health` | 检查 API、数据库、缓存和 worker 状态 |
| 12 | 实时事件 | `WebSocket /ws/v1` | 推送新消息与状态变化，支持游标补拉 |

## 2. 接口详情

### 2.1 登录

| 项目 | 内容 |
|---|---|
| 接口名称 | 登录 |
| 接口路由 | `POST /api/v1/auth/login` |
| 请求方式 | HTTP POST |
| 涉及数据表 | `users` |
| 请求参数 | `username`、`password` |
| 返回示例 | `{"user_id":1,"username":"liaojunjian","display_name":"廖俊健","session_expires_at":"2026-11-20T10:00:00+08:00"}` |
| 主要错误 | 401：账号或口令错误 |

### 2.2 退出登录

| 项目 | 内容 |
|---|---|
| 接口名称 | 退出登录 |
| 接口路由 | `POST /api/v1/auth/logout` |
| 请求方式 | HTTP POST |
| 涉及数据表 | 不直接修改业务表；注销当前登录会话 |
| 请求参数 | 无业务请求体；会话信息由认证上下文提供 |
| 返回示例 | `{"ok":true}` |
| 主要错误 | 401：未认证或会话已失效 |

### 2.3 当前用户

| 项目 | 内容 |
|---|---|
| 接口名称 | 当前用户 |
| 接口路由 | `GET /api/v1/auth/me` |
| 请求方式 | HTTP GET |
| 涉及数据表 | `users` |
| 请求参数 | 无业务请求参数；会话信息由认证上下文提供 |
| 返回示例 | `{"user_id":1,"username":"liaojunjian","display_name":"廖俊健","session_expires_at":"2026-11-20T10:00:00+08:00"}` |
| 主要错误 | 401：未认证或会话已失效 |

### 2.4 消息列表

| 项目 | 内容 |
|---|---|
| 接口名称 | 消息列表 |
| 接口路由 | `GET /api/v1/messages` |
| 请求方式 | HTTP GET |
| 涉及数据表 | `messages`、`conversations` |
| 请求参数 | `platform`、`conversationId`、`status`、`cursor`（状态历史自增 ID，补拉该值之后有新建或状态变化的消息）、`limit` |
| 返回示例 | `{"items":[{"schema_version":"1.0.0","message_id":10482,"platform":"dingtalk","conversation":{"id":501,"platform_conversation_id":"cid-test-001","title":"测试会话","conversation_type":"group"},"sender_name":"测试用户","message_type":"text","content_text":"请确认今天的发货清单","direction":"inbound","status":"stored","occurred_at":"2026-11-20T09:40:00+08:00","version":1,"client_request_id":null}],"next_cursor":12482}` |
| 主要错误 | 401：未认证；422：参数不合法 |

### 2.5 消息详情

| 项目 | 内容 |
|---|---|
| 接口名称 | 消息详情 |
| 接口路由 | `GET /api/v1/messages/{messageId}` |
| 请求方式 | HTTP GET |
| 涉及数据表 | `messages`、`conversations`、`attachments`、`message_status_history` |
| 请求参数 | 路径参数 `messageId` |
| 返回示例 | `{"schema_version":"1.0.0","message_id":10482,"platform":"dingtalk","conversation":{"id":501,"platform_conversation_id":"cid-test-001","title":"测试会话","conversation_type":"group"},"sender_name":"测试用户","message_type":"text","content_text":"请确认今天的发货清单","direction":"inbound","status":"processed","occurred_at":"2026-11-20T09:40:00+08:00","version":3,"client_request_id":null,"status_history":[{"from_status":"displayed","to_status":"processed","reason":"用户确认处理","actor":"user","occurred_at":"2026-11-20T09:41:18+08:00"}]}` |
| 主要错误 | 404：消息不存在 |

### 2.6 标记处理

| 项目 | 内容 |
|---|---|
| 接口名称 | 标记处理 |
| 接口路由 | `POST /api/v1/messages/{messageId}/process` |
| 请求方式 | HTTP POST |
| 涉及数据表 | `messages`、`message_status_history` |
| 请求参数 | `version`、`note` |
| 返回示例 | `{"schema_version":"1.0.0","message_id":10482,"platform":"dingtalk","conversation":{"id":501,"platform_conversation_id":"cid-test-001","title":"测试会话","conversation_type":"group"},"sender_name":"测试用户","message_type":"text","content_text":"请确认今天的发货清单","direction":"inbound","status":"processed","occurred_at":"2026-11-20T09:40:00+08:00","version":3,"client_request_id":null}` |
| 主要错误 | 409：版本冲突或状态不允许流转 |

### 2.7 回复消息

| 项目 | 内容 |
|---|---|
| 接口名称 | 回复消息 |
| 接口路由 | `POST /api/v1/messages/{messageId}/reply` |
| 请求方式 | HTTP POST |
| 涉及数据表 | `messages`、`attachments`、`message_status_history`、`outbox_events` |
| 请求参数 | `client_request_id`、`message_type`、`text`、`attachments` |
| 请求示例 | `{"client_request_id":"reply-10482-7f3a","message_type":"text","text":"收到，我会在 10:30 前核对。"}` |
| 返回示例 | `{"message_id":10501,"status":"replying","accepted_at":"2026-11-20T09:42:00+08:00"}` |
| 主要错误 | 409：重复回复请求或状态冲突 |

### 2.8 重试发送

| 项目 | 内容 |
|---|---|
| 接口名称 | 重试发送 |
| 接口路由 | `POST /api/v1/messages/{messageId}/retry` |
| 请求方式 | HTTP POST |
| 涉及数据表 | `messages`、`outbox_events`、`message_status_history` |
| 请求参数 | `reason` |
| 返回示例 | `{"message_id":10501,"status":"replying","accepted_at":"2026-11-20T09:45:30+08:00"}` |
| 主要错误 | 409：当前状态不允许重试 |

### 2.9 待办列表

| 项目 | 内容 |
|---|---|
| 接口名称 | 待办列表 |
| 接口路由 | `GET /api/v1/todos` |
| 请求方式 | HTTP GET |
| 涉及数据表 | `messages`、`conversations` |
| 请求参数 | `platform`、`status`、`limit` |
| 返回示例 | `{"items":[{"message_id":10490,"platform":"dingtalk","title":"付款申请审批","status":"pending","occurred_at":"2026-11-20T09:38:00+08:00"}]}` |

状态映射：接口层 `pending` 对应数据库中 `message_type=todo` 且消息状态为 `received`、`stored` 或 `displayed` 的记录；`processed` 对应消息状态为 `processed` 的记录。其他异常、回复中或已确认消息仍通过消息中心按真实消息状态查询，不在待办列表中改写状态。

### 2.10 平台 Webhook

| 项目 | 内容 |
|---|---|
| 接口名称 | 平台 Webhook |
| 接口路由 | `POST /webhooks/{platform}` |
| 请求方式 | HTTP POST |
| 涉及数据表 | `platform_accounts`、`conversations`、`messages`、`message_status_history` |
| 请求参数 | 平台原始事件 JSON；签名信息位于平台规定的请求头 |
| 返回示例 | `{"ok":true}` |
| 主要错误 | 400：格式不合法；401：验签失败；409：重复事件 |

### 2.11 健康检查

| 项目 | 内容 |
|---|---|
| 接口名称 | 健康检查 |
| 接口路由 | `GET /api/v1/health` |
| 请求方式 | HTTP GET |
| 涉及数据表 | 不直接修改业务表；检查 `messages` 所在数据库连接 |
| 返回示例 | `{"status":"ok","checks":{"database":"ok","redis":"ok","worker":"ok"}}` |

### 2.12 WebSocket 实时事件

| 项目 | 内容 |
|---|---|
| 接口名称 | 实时事件 |
| 接口路由 | `WebSocket /ws/v1` |
| 请求方式 | WebSocket |
| 涉及数据表 | `messages`、`message_status_history` |
| 事件格式 | `{"schema_version":"1.0.0","event_id":"evt_01","cursor":12482,"type":"message.status_changed","data":{"message_id":10482,"to_status":"processed"}}` |
| 恢复方式 | 游标取 `message_status_history.id`；断线后通过 `GET /api/v1/messages?cursor=<last_cursor>` 补拉该值之后有新建或状态变化的消息 |

## 3. 其他

AI 专项对话链接：待替换为真实、可公开访问且不含隐私信息的链接。

接口契约已通过本地 OpenAPI 解析校验，命令为 `python .harness/scripts/harness.py openapi contracts/openapi.json`，退出码 0；4 个关键响应示例另经 `python output/validate_openapi_examples.py` 校验通过，退出码 0。两项证据位于 `docs/submissions/assets/validation/evidence-05-contract-validation-01.txt`。该结果仅证明契约和示例一致性，不代表接口已实现。所有请求与返回示例均为虚构示例，不对应真实用户、消息或平台数据。