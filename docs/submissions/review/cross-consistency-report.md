# 跨文档一致性复核记录

> 复核时间：2026-11-20；复核范围：本轮 7 份提交源稿、`docs/submissions/preliminary-design.md`、`contracts/`、契约验证证据和发布成品。全程排除 `demo`。

## 1. 已复核一致的内容

- `01`～`05` 一级章节与提交计划要求一致；可行性含技术、数据、时间三维及难点预案；精简设计含业务闭环、架构、接口、表结构和状态机。
- 数据库 7 张表、字段和 SQL 与 `contracts/schema.sql` 一致；数据库成品已逐表嵌入 7 条可执行 `CREATE TABLE` 语句。
- 接口清单 12 项与详情 12 项一致；已补齐退出登录、当前用户。
- 消息 JSON Schema、DDL、OpenAPI 和精简设计中的 11 个消息状态一致。
- 技术栈统一为 Vue 3 + TypeScript + Vite + Element Plus、FastAPI + SQLAlchemy 2 + Alembic、MySQL 8、Redis 7、REST/OpenAPI 3.1 + WebSocket、Docker Compose + Nginx；均注明为设计选型，不代表实现完成。
- 原型图明确标注为静态原型，不冒充真实产品证据；真实验证只纳入契约命令日志、实际输出、退出码和原型呈现截图。
- 用户陈述的钉钉接通状态已加归属和“证据待归档、当前未复核”限定；飞书未接通、统一 Web 未实现、无演示视频均如实记录。
- 精简设计中的路径参数已统一为 `{messageId}`；登录与接口响应示例已改为中性虚构身份。
- `docs/submissions/preliminary-design.md` 与 `source/06-preliminary-design.md` 的关键路由参数、事实边界已同步。

## 2. 已修正的契约冲突

1. `MessageDetail` 原 `allOf` 与两个 `additionalProperties:false` 互相排斥；现拆为 `UnifiedMessageBase`，普通消息与详情消息分别用 `unevaluatedProperties:false` 闭合。
2. 登录和平台 Webhook 现显式设置 `security: []`，不再被全局统一入口会话 Cookie 误覆盖。
3. 消息 Schema 的内部 `message_id` 统一为整数或空值，与 DDL 的 `BIGINT UNSIGNED` 和 OpenAPI 的 `integer` 对齐。
4. 消息列表、详情、处理和待办示例补齐全部必填字段；接口层 `pending/processed` 与数据库消息状态的映射已明确。
5. 状态历史自增 ID 明确为全局递增事件游标，覆盖新消息与状态变化；需求、接口、WebSocket、数据模型和数据库文档已同步。
6. 用户与状态历史、outbox 与消息的外键口径改为逻辑关联说明，避免 ER 图与 DDL 不一致。

## 3. 机器与结构复核结果

- `python .harness/scripts/harness.py json contracts/message.schema.json`：退出码 0。
- `python .harness/scripts/harness.py openapi contracts/openapi.json`：退出码 0。
- `python output/validate_openapi_examples.py`：4/4 响应示例通过必填字段、类型、枚举和属性闭合校验，退出码 0。
- 7 份 HTML 版式门禁全部通过；7 份 Word 的预检、页面要素、目录域、PAGEREF、分节、标题样式绑定和内容完整性校验均通过。
- `00_提交清单.xlsx` 的 8 行与实际发布文件一一对应，边框、对齐、行高经独立复核并修正；无公式、无错误值。

## 4. 未消除的事实边界

- 准备计划写于技术选型和报名信息确认前，其中“待确认”状态与当前用户已确认事实存在时间差；本次以用户确认后的 `submission-metadata.md` 和提交源稿为提交口径，未修改原始计划。
- 当前仍无飞书接通、统一 Web 产品源码、干净 checkout 运行记录、钉钉可归档证据、PDF 成品、真实 AI 链接和实测页数；详见 `open-issues.md`。

结论：设计资料内部一致性已达到本次可整理范围；真实实现与验证证据仍不足，不能标记为官方最终验收完成。
