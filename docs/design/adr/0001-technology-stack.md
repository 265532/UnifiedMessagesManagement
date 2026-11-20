# ADR-0001：初赛技术选型

| 项 | 内容 |
|---|---|
| 状态 | 已由用户确认，用于初赛设计稿 |
| 日期 | 2026-11-20 |
| 决策人 | 用户确认；Arch-Agent 整理 |
| 适用范围 | 初赛设计文档、原型、数据库与接口契约 |

## 背景

项目需要在统一 Web 入口完成“消息接收 → 展示 → 处理 → 回复 → 状态回流”闭环。当前仓库没有可复用产品代码；钉钉仅有平台侧接通事实，统一 Web 产品尚未实现；飞书尚未接通。AI 摘要、第三平台扩展和高可用均不进入初赛 Must 闭环。

## 决策

- 前端：Vue 3、TypeScript、Vite、Element Plus。
- 后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、Alembic。
- 数据库：MySQL 8，作为消息、状态、幂等约束和待发送记录的唯一事实源。
- 缓存：Redis 7，用于登录会话、平台 Token 缓存和短期协调，不保存最终业务状态。
- 接口：REST `/api/v1`、WebSocket `/ws/v1`、OpenAPI 3.1、JSON Schema 2020-12。
- 发送与补偿：模块化单体中的独立 worker；业务写入与 outbox 记录使用同一数据库事务。
- 反向代理：Nginx，用于托管前端、反向代理 REST/WebSocket，并在部署环境终止 HTTPS。
- 部署：Docker Compose，服务为 `web`、`api`、`worker`、`mysql`、`redis`、`nginx`。
- AI：不进入初赛主闭环；后续作为 Could 项另行评审。

## 备选方案

Java 21 + Spring Boot 3 + React + MySQL 8 + Redis 7。该方案更适合既有 Java 代码或团队 Java 经验更强的情形；当前仓库没有既有产品代码，因此未选择。

## 结果与约束

1. MySQL 唯一约束承担事件幂等与回复请求幂等；Redis 不能替代数据库约束。
2. WebSocket 只负责推送通知；断线恢复通过 REST 游标补拉。
3. 平台发送 HTTP 成功只能进入 `replied`；只有真实回执或平台查询补偿结果才能进入 `confirmed`。
4. 文件消息先保存元数据，再按平台规范上传素材并发送。
5. 会话 Cookie 使用 `HttpOnly`、`Secure`、`SameSite`，空闲 30 分钟失效；WebSocket 同样鉴权。
6. 本 ADR 是设计基线，不代表实现、部署或平台验证已完成。