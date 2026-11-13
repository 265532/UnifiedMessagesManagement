# 项目 Harness 工程设计

版本：v1.0
日期：2026-11-13
状态：已批准实施（用户指定 DeepSeek Harness 为参考，结合标准 Git + CI）

## 1. 目标与边界

目标是把 `docs/index.md` 中的角色编排和质量门转换为可跨 AI 工具持续执行的工程系统：

- 同一仓库保存唯一任务状态、角色权限、验证规则和交接记录；
- DeepSeek Harness（DSH）、WorkBuddy、其他 IDE Agent 或纯人工都执行同一协议；
- 任务完成必须由文件、命令和人工批准等外部证据证明，不能由模型自称完成；
- 质量门在本地和 CI 使用同一个命令，失败时给出可定位原因；
- 所有产品实现技术栈仍由 Phase 2 ADR 决定，Harness 不预选 Java、Node.js 或 Python。

非目标：本层不代替产品代码，不伪造账号截图或测试证据，不声称 DSH 私有配置格式可直接导入。

## 2. 方案选择

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 仅编写 DSH 专用编排配置 | 在单一工具内直接 | 切换工具即丢失状态与门禁，且依赖未公开稳定的配置格式 | 否决 |
| 仅使用 GitHub Projects / CI | 标准化 | 与 AI 角色、上下文和交接协议脱节 | 否决 |
| 仓库内工具无关 Harness + DSH 适配层 | 状态可移植、本地与 CI 同构、DSH 可复用结构化输出 | 需要维护少量 CLI 和 JSON | **采用** |

## 3. 唯一事实源顺序

1. 赛题原文与经批准的需求基线；
2. `.harness/feature_list.json`：任务、依赖、当前通过状态；
3. `.harness/gates.json`：G0–G6 的可执行验收规则；
4. `.harness/roles.json` 与 `.harness/roles/*.md`：角色权限与上下文；
5. `contracts/`、`docs/design/`、源码与测试：实际交付物；
6. `.harness/evidence/`：机器或人工产生的验证证据；
7. `.harness/progress.md`：会话交接摘要，只用于导航，不替代任务状态；
8. `docs/index.md`：原始管理计划；日期与任务状态以 `.harness/execution-plan.json` 和任务清单为准。

禁止用聊天记录、口头说明或 Agent 报告覆盖上述事实源。

## 4. 核心不变量

- `passes` 只能是布尔值；`verify` 成功后才允许由 `false` 变为 `true`。
- 每个任务必须有 DoD；实现类任务在开工前必须补齐可执行 `verification`，否则拒绝验证。
- 文件证据记录 SHA-256；文件变化后，旧的通过结论失效。
- `verify` 另写 `.harness/evidence/<TASK_ID>/result.json`，`feature_list.json` 保存该归档的 SHA-256 指针；两者不一致即失败，避免只有一处可手工改动的完成声明。门禁结果同样由 `.harness/gate_state.json` 保存 SHA-256 指针。
- 所有 `passes=false→true` 的状态变化都由 CI 的 `history` 与 Git 历史交叉核验：证据必须随提交保存，其 `git_head` 必须位于被检查的提交历史中。仓库内的两个文件仍可能被协同伪造，因此外部信任锚是 `.github/CODEOWNERS`、分支保护和必需状态检查；这不是可选的管理建议，而是 Harness 信任模型的一部分。
- 命令证据保存命令、退出码和输出尾部；`feature_list.json` 仅保存命令与退出码，完整输出留在 evidence。CI 会重新执行已声明通过的任务。
- `human_required=true` 的任务必须保存人工批准人和证据；人工质量门也必须把批准人、命令退出码与结果写入 `.harness/evidence/<gate>/result.json`，AI 不得代为批准。
- 任务依赖构成验收链：上游 `passes` 回退为 `false` 时，下游通过态必须失效并重新验证。
- DSH 停止原因只有 `completed` 可对应任务完成；`aborted/error/max-tokens/refusal` 均按失败或受阻处理。
- 报告中的 `status=completed` 不等于任务通过，仍须运行 `verify` 和对应质量门。
- 任一任务最多自动重试 2 次；连续 2 次无进展、验证信号不变或触及预算即停止并升级。
- 契约冻结后，修改 `contracts/`、任务 DoD 或门禁规则必须由 Super Agent 审查并在进度日志记录。

## 5. 目录与运行接口

```text
AGENTS.md                       所有 AI 工具首先读取的工作协议
.harness/
  project.json                  项目元信息、预算和路径
  execution-plan.json           重排后的阶段日期与范围
  feature_list.json             唯一任务状态
  roles.json + roles/           角色权限与 persona
  gates.json                    G0–G6 门禁
  schemas/                      外部工具可用的 JSON Schema
  templates/                    报告与会话交接模板
  scripts/harness.py            标准库 CLI
  scripts/test_harness.py       CLI 单元测试
  dsh/                          DeepSeek Harness 适配说明
  evidence/                     任务与门禁证据
  progress.md                   最新会话交接与历史摘要
.github/workflows/harness.yml   GitHub Actions；其他 CI 调用相同命令
init.sh / init.ps1              跨平台初始化入口
```

常用接口：

```bash
python .harness/scripts/harness.py doctor
python .harness/scripts/harness.py validate
python .harness/scripts/harness.py status
python .harness/scripts/harness.py verify RA-01
python .harness/scripts/harness.py gate G1
python .harness/scripts/harness.py ci
python -m unittest .harness/scripts/test_harness.py
```

## 6. 会话协议

每个新会话必须：读取 `AGENTS.md` → 运行 `doctor/status` → 阅读 Git 日志和 `progress.md` → 选择一个已解锁任务 → 核对验证规则 → 小步实现并验证 → 提交 → 更新交接。

禁止一次领取多个相互无关任务；禁止删除任务、修改验收描述或把失败测试改弱来取得通过。

## 7. DSH 适配

DSH 负责提供模型、Subagent、Skill 和工具运行环境，但不持有权威项目状态。每个 Subagent 使用对应 `.harness/roles/*.md` 作为 persona，并绑定 `.harness/schemas/agent-report.schema.json` 的结构化输出要求。编排遵循任务依赖，飞书与钉钉 Adapter 在契约冻结后可并行。DSH 的输出精简只传递报告 JSON 与必要产物路径，完整文档留在仓库中，避免长链上下文膨胀。

## 8. 当前基线与重排

2026-11-13 实测基线：仓库只有两个文档初始化提交，无产品代码；G0 的账号清单与连通证据未归档；G1 的需求分析文档存在；G2 设计交付物未归档。因此原计划 M1=11/13 不再作为承诺日期。

重排原则：11/13 完成 G0 状态确认与 G2 契约，11/16 飞书纵切，11/18 双平台，11/19 状态回流，11/20 初赛提交；钉钉与前端在契约后并行，企微、AI 摘要和高可用均不阻塞初赛。具体日期见 `.harness/execution-plan.json`。

## 9. 验证策略

先写 CLI 失败测试，再实现功能。26 个测试覆盖：有效清单、重复任务 ID、未知依赖、非布尔状态、未定义验证规则、文件哈希失效、依赖回退级联失效、独立验证归档与篡改检测、人工批准缺失、人工/失败门禁归档及哈希指针、空门禁定义防洗白、非 completed 停止原因、已跟踪与未跟踪文件密钥扫描、质量门失败和通过、OpenAPI 最小结构、连通证据哈希、Git 历史状态锚点、解释器替换、glob 白名单以及 Docker 可选性。交付前运行单元测试、结构校验、密钥扫描、状态输出、历史锚点及实际门禁负向检查，保留命令结果。
