# DeepSeek Harness 适配层

本目录提供 DSH 的运行映射，**不是声称可直接导入的 DSH 私有配置包**。不同 DSH 版本的界面和插件字段可能变化，因此权威状态始终保存在仓库 JSON 与证据中。若当前版本支持对应能力，按下面映射配置；不支持时由主 Agent 执行同样协议。

## 1. 上下文与角色

1. 将仓库根 `AGENTS.md` 放在项目约定/根上下文位置，保持常驻。
2. 为需要的角色创建 Subagent，persona 使用 `.harness/roles/<role>.md`；不要一次启动全部角色。
3. 每次只附加当前任务 JSON、相关契约和上次交接。完整需求文档按需读取，不作为所有 Subagent 的常驻上下文。
4. Skill 只绑定当前角色需要的文件编辑、终端、测试或网页能力；角色权限以 `roles.json` 为上限。
5. 开启输出精简时，只向下游传递报告 JSON、产物路径、失败原因和下一动作，不传递完整闲聊或大段文档。

## 2. 结构化输出

Subagent 输出遵循 `.harness/schemas/agent-report.schema.json`。模板位于 `.harness/templates/agent-report.json`，默认是 blocked，防止未修改模板被误当完成证据。

| DSH stop_reason | Harness 处理 |
|---|---|
| `completed` | 仅允许 `status=completed`，随后仍须运行 `verify` |
| `aborted` | blocked/failed，不得进入完成态 |
| `error` | failed，保留错误并诊断 |
| `max-tokens` | blocked，缩小下一次任务范围，不得把半截输出当成功 |
| `refusal` | blocked，检查权限、安全边界或任务描述 |

建议用 `phase()/log()` 等进度能力报告任务 ID 和验证阶段；具体可用名称以当前 DSH 版本为准。Harness 不依赖这些名称保存状态。

## 3. 编排顺序

```text
G0/G1 → G2 契约
           ├─ IM-01 → IM-02 ─┬─ IM-03 飞书 ─┐
           │                 └─ IM-04 钉钉 ─┤（接口满足后二者可并行）
           └─ DS-06 → IM-05 前端 ────────────┤
                                             └─ IM-06 → QA/G4
```

- 只有确实需要全部上游结果时才使用全屏障并行；独立任务用流水线/并行，默认最多 3 个实现角色同时写代码。
- Super Agent 在每个任务结束后运行 `report`，随后独立运行 `verify <TASK_ID>`，不能用 Subagent 自评替代。
- IM-03/IM-04 的真实平台发送需要人工批准；Mock 测试通过不得写成真实平台通过。
- 每个任务最多自动重试 2 次；连续两轮没有新证据即停止并升级。

## 4. 单次任务的执行封装

```bash
# 主 Agent 保存 Subagent 的结构化结果后
python .harness/scripts/harness.py report path/to/report.json

# 独立验证；只有成功才会把 passes 置为 true
python .harness/scripts/harness.py verify TASK_ID

# 阶段完成后运行门禁；需要人工的门禁提供真实批准人。
# 成功和失败都会归档到 .harness/evidence/<gate>/result.json，需随提交保留。
python .harness/scripts/harness.py gate G2
```

真实文件和命令是跨工具接口。DSH 崩溃、更换模型或更换工具后，新会话从 `AGENTS.md` 的启动仪式恢复，不从聊天摘要猜测状态。

## 5. 切换到其他 AI 工具

其他工具无需模拟 DSH：读取根 AGENTS.md 和角色文件，按同一任务 JSON 工作，输出同一报告，调用同一 CLI。若另一工具不支持结构化输出，可让主 Agent 把结果整理为报告 JSON，但仍须通过独立命令验证。
