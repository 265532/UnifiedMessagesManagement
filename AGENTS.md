# AGENTS.md · UnifiedMessagesManagement

本文件适用于所有 AI 编程工具与人工贡献者。任何 Agent 进入本仓库后，先读本文件，再读对应 `.harness/roles/<role>.md`。不要依赖上一段聊天记忆判断项目状态。

## 1. 项目目标与红线

目标是在统一 Web 入口完成“消息接收 → 展示 → 处理 → 回复 → 状态回流”，并可在纯净 Linux 环境独立部署。禁止只做单向接收或简单转发；禁止虚构平台连通、测试、部署或页数证据；禁止对人员进行追踪或信息收集。

## 2. 唯一事实源

按以下顺序判断，冲突时不得自行选择最有利的一份：

1. 赛题原文和已批准需求基线；
2. `.harness/feature_list.json` 的任务、依赖和 `passes`；
3. `.harness/gates.json` 的质量门；
4. `.harness/roles.json` 的权限；
5. `contracts/`、`docs/design/`、源码、测试和 `.harness/evidence/`；
6. `.harness/progress.md` 的交接导航；
7. `docs/index.md` 的原始管理计划。

日期与范围以 `.harness/execution-plan.json` 为准。任务报告和聊天记录不是事实源。

## 3. 每次会话的启动仪式

```bash
python .harness/scripts/harness.py doctor
python .harness/scripts/harness.py validate
python .harness/scripts/harness.py status
git log --oneline -8
```

然后阅读 `.harness/progress.md`、本任务 DoD 和验证规则，运行现有测试或服务确认基线。**一次只选择一个已解锁的主任务**；不要重建整个项目，不要一次性实现所有 Phase。

## 4. 完成定义

- `passes` 只能由 `python .harness/scripts/harness.py verify <TASK_ID>` 修改，禁止手工编辑。
- Agent 报告中的 `status=completed` 仅表示执行结束，不表示任务通过。
- `verification.ready=false` 时不得开工实现；先由 Arch/Super 根据选定技术栈补齐文件、命令和阈值，并单独提交验证规则。
- 文件证据使用 SHA-256；内容改变后必须重新验证。命令证据必须可重跑并保存退出码。
- 每次 `verify` 都会生成 `.harness/evidence/<TASK_ID>/result.json`；`feature_list.json` 只保存该记录的 SHA-256 指针和不回显输出的命令摘要。通过状态与该独立记录不一致时，CI 必须失败。记录还绑定当时的 Git HEAD；CI 的 `history` 会检查所有 `false→true` 状态变化确有随提交保存、且绑定本段历史的证据。
- 仓库内文件无法挡住「同时改写 feature_list、evidence 并提交」的协同伪造。外部信任锚是 `.github/CODEOWNERS` + `main` 分支保护（强制 PR、Owner 审查、必需 CI 状态检查）；不得绕过保护直接提交状态文件。
- 不得删除任务、改写任务描述、降低阈值或删除失败用例来取得通过。
- `human_required=true` 的任务必须使用 `--human-approved-by <姓名>`，AI 不得代填批准人。
- 对应质量门通过前，不得声称 Phase 完成；`gate` 命令先执行完整结构/证据校验，再把本次结果、命令输出和人工批准人归档到 `.harness/evidence/<gate>/result.json`，并在 `.harness/gate_state.json` 写入该归档的 SHA-256 指针。在 GitHub Actions 手动运行门禁时，还必须下载 `gate-evidence-*` artifact 并由人工随后续提交归档。
- 上游依赖回退为未通过时，下游任务的 `passes` 自动失效，必须重新验证；不得只恢复上游后沿用旧的下游结论。

## 5. 角色与权限

角色是“persona + 工具范围 + 可写路径”，不是 7 个必须常驻的模型实例。一个工具可以实现多个角色，但同一任务的建议者与独立验证者应尽量分开。

- Super Agent：编排、审查、集成与升级，不替执行 Agent 自评。
- RA / Arch：维护需求与契约；G2 后契约变更必须记录 ADR 和审批。
- Dev-Core / Dev-Connector / Dev-FE：只在角色允许路径内实现，并附带测试。
- QA：可以新增测试和故障注入，不得通过修改产品代码让测试假绿。
- DevOps：部署与健康检查，不做未批准的系统级修改或远程发布。

具体可写路径见 `.harness/roles.json`。越界时停止并请求 Super Agent 调整任务，不要静默扩大权限。

## 6. 工具与人工审批

以下动作必须先取得明确人工批准：真实账号或权限申请、向非测试企业/真实用户发消息、远程 push/发布、系统级安装、删除或重置数据环境、绕过失败门禁。密钥只能来自环境变量或本地 `.env`，不得写入 Git、报告、截图或日志。

高风险操作默认使用测试企业和最小权限。无法确认影响范围时，选择只读操作并升级给人。

## 7. 停止与失败恢复

- 同一任务最多自动重试 2 次；连续 2 次无新证据、重复同一错误或验证信号不变即停止。
- 达到会话时间/token 预算、权限不足、外部账号未就绪或需要修改他人任务时，标记受阻并交接。
- 不隐藏失败，不无限反思，不反复重写同一文件。第二次失败应改变诊断方法，而不是原样重试。
- DSH 的 `aborted/error/max-tokens/refusal` 全部按未完成处理；只有 `completed` 可以进入后续 `verify`。

## 8. 上下文管理

只向子 Agent 提供：本角色文件、当前任务 JSON、必要契约/接口、相关源码和上次交接。不要把全部历史对话或所有文档塞入每个角色。长文档按需读取；串联编排只传结构化报告与产物路径，完整内容留在仓库。

## 9. Git 纪律

- 小步提交，一次提交只对应一个任务或一个明确的 Harness 变更。
- 提交前运行 `python .harness/scripts/harness.py pre-commit`。
- 不提交 `.env`、密钥、无关大文件或临时日志；不修改历史伪造进度。
- 结束会话前更新 `.harness/progress.md` 的“当前交接”，写清唯一推荐下一动作。
- 未经用户明确批准，不 push、不发布、不强制覆盖远程。
- `verification.commands` 只写跨平台可重跑的简单命令；以 `python ` 开头的命令会由 CLI 自动替换为当前解释器，不要依赖 shell 专有的重定向、环境变量或 `&&` 链式语法。

## 10. 常用命令

```bash
# 状态与验证
python .harness/scripts/harness.py status
python .harness/scripts/harness.py status --json
python .harness/scripts/harness.py verify RA-01
python .harness/scripts/harness.py gate G1

# 结构化报告与人工任务
python .harness/scripts/harness.py report path/to/report.json
python .harness/scripts/harness.py verify IM-03 --human-approved-by "真实姓名"

# 本地与 CI 同一入口
python .harness/scripts/harness.py ci
python -m unittest discover -s .harness/scripts -p "test_*.py"
```

DSH 的具体映射见 `.harness/dsh/README.md`；其他工具直接执行本协议，不需要模拟 DSH 私有 API。
