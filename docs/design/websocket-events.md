# WebSocket 事件契约（初赛设计稿）

> 地址：`/ws/v1`。认证方式复用登录会话 Cookie，服务端校验 Origin。设计稿，不代表实现完成。

## 1. 通用事件格式

```json
{
  "schema_version": "1.0.0",
  "event_id": "evt_01J...",
  "cursor": 12345,
  "type": "message.status_changed",
  "occurred_at": "2026-11-20T09:30:00+08:00",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 事件格式版本 |
| `event_id` | string | 事件唯一 ID |
| `cursor` | integer | 全局单调递增游标，取本次状态历史记录 `message_status_history.id`，用于断线补拉 |
| `type` | string | 事件类型 |
| `occurred_at` | date-time | 事件发生时间 |
| `data` | object | 事件数据 |

## 2. 事件类型

| 事件类型 | 触发时机 | 核心数据 |
|---|---|---|
| `message.created` | 新消息入库 | `message` |
| `message.status_changed` | 状态机流转 | `message_id`、`from_status`、`to_status`、`version` |
| `message.reply_accepted` | 回复进入发送队列 | `message_id`、`client_request_id` |
| `message.send_failed` | 平台发送失败 | `message_id`、`error`、`retryable` |
| `connection.ready` | 连接建立 | `cursor`、`server_time` |

## 3. 断线恢复

前端保存最后收到的 `cursor`。每条新消息入库时必须至少写入一条初始状态历史，后续每次状态变化也写入新历史记录，因此 `message_status_history.id` 可以覆盖新建消息与状态变化两类事件。重连后先建立 WebSocket，再调用 `GET /api/v1/messages?cursor=<cursor>` 查询该游标之后有新建或状态变化的消息，并按 `cursor` 与推送事件去重。WebSocket 不可用时可降级为定时轮询，但不改变服务端状态机。