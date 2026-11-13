# UnifiedMessagesManagement

多平台连接器与统一消息管理：在统一 Web 入口完成飞书、钉钉等平台的消息接收、集中展示、处理、回复和状态回流，并提供可独立部署的比赛作品。

## 项目 Harness

本仓库包含工具无关的 Harness 工程。DeepSeek Harness、WorkBuddy、其他 IDE Agent 或人工都使用同一份任务状态、角色权限、验证规则与交接协议，不依赖某个聊天会话的记忆。

### 初始化

```bash
# Linux / macOS / Git Bash
./init.sh

# Windows PowerShell
./init.ps1
```

或直接运行：

```bash
python .harness/scripts/harness.py bootstrap
python .harness/scripts/harness.py status
```

### 每个 AI 会话的入口

1. 阅读 `AGENTS.md` 和对应 `.harness/roles/*.md`。
2. 运行 `doctor`、`validate`、`status`，查看 Git 日志和 `.harness/progress.md`。
3. 只领取一个已解锁任务；`verification.ready=false` 时先补验证规则。
4. 用实际文件和可重跑命令验证，不手工修改 `passes`。
5. 更新交接并小步提交；未经明确批准不 push、不发布、不向真实用户发消息。

### 常用命令

```bash
python .harness/scripts/harness.py status
python .harness/scripts/harness.py verify TASK_ID
python .harness/scripts/harness.py gate G1
python .harness/scripts/harness.py ci
python -m unittest discover -s .harness/scripts -p "test_*.py"
```

人工任务额外使用 `--human-approved-by "真实姓名"`。DSH 角色与结构化输出映射见 `.harness/dsh/README.md`。

**外部信任锚**：GitHub 的 `main` 分支应启用强制 PR、CODEOWNERS Owner 审查和 `harness` 必需状态检查，配置见 `.github/CODEOWNERS`。CI 会运行 `history <BASE> HEAD`，把每个 `passes=false→true` 状态变化绑定到 Git 提交和独立证据；仓库内文件不能替代分支保护。

## 文档与当前计划

- `docs/index.md`：原始 Super Agent 管理计划。
- `docs/需求分析文档.md`：需求基线候选。
- `docs/harness-design.md`：Harness 架构与不变量。
- `.harness/execution-plan.json`：2026-11-13 重排后的当前执行计划。
- `contracts/` 与 `docs/design/`：G2 可执行契约和设计交付物。

**当前不是产品完成态。** Harness 初次建立时任务为 0/33；G0 需要人工账号/连通证据，G1/G2 需按依赖逐步验证。实时状态以 `status` 命令为准。
