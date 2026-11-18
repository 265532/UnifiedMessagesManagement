# 可执行契约

G2 需要在本目录形成以下实际文件，而不是只在文档里描述：

- `message.schema.json`：统一消息 JSON Schema，含版本号与双平台映射所需字段。
- `openapi.json`：OpenAPI 3.x；REST 操作必须有响应定义，WebSocket 扩展与事件契约可在同文件扩展字段或链接文档中描述。
- `schema.sql`：DDL、幂等唯一约束与查询索引。

校验命令：

```bash
python .harness/scripts/harness.py json contracts/message.schema.json
python .harness/scripts/harness.py openapi contracts/openapi.json
python .harness/scripts/harness.py gate G2
```

G2 冻结后，任何契约变更必须先写 ADR、评估核心/连接器/前端/QA 影响并取得 Super Agent 审批，再更新相关任务验证。禁止为了适配某个实现而静默降低契约要求。
