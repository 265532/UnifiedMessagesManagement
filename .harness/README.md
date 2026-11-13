# 项目 Harness

这是跨 AI 工具的执行层。先看根目录 `AGENTS.md`，设计理由见 `docs/harness-design.md`，DSH 映射见 `dsh/README.md`。

## 状态文件分工

| 文件 | 用途 | 是否可手工改 |
|---|---|---|
| `feature_list.json` | 任务、依赖、DoD、验证规则、通过状态 | 可维护任务和验证规则；**不得手工改 passes** |
| `gates.json` | G0–G6 必需任务与命令 | 仅经 Super Agent 审查 |
| `gate_state.json` | 每个门禁最新结果归档的 SHA-256 指针与结论 | 只能由 `gate` 命令更新 |
| `execution-plan.json` | 当前日期、范围与里程碑 | 变更须保留历史原因 |
| `roles.json` / `roles/` | 工具权限与 persona | 权限扩大须审批 |
| `evidence/` | 验证、截图、门禁结果、演练等证据 | 只允许追加真实证据；失败记录也提交保留 |
| `progress.md` | 会话交接导航 | 每会话更新，不能代替任务状态 |

## 最小闭环

```bash
python .harness/scripts/harness.py doctor
python .harness/scripts/harness.py status
# 完成一个已解锁任务后
python .harness/scripts/harness.py report path/to/report.json
python .harness/scripts/harness.py verify TASK_ID
python .harness/scripts/harness.py gate GX
```

本地 `ci` 与 GitHub Actions 使用同一命令。其他 CI 只需安装 Python 3.10+，依次运行单元测试和 `python .harness/scripts/harness.py ci`。GitHub Actions 额外运行 `history <BASE> HEAD` 校验提交历史中的状态跃迁；本地提交后可执行 `python .harness/scripts/harness.py history HEAD^ HEAD`。在 GitHub Actions 手动执行门禁后，下载 `gate-evidence-*` artifact 并将真实结果随后续提交归档，避免批准记录只存在于临时 runner。

连通截图归档后，必须把哈希写入 `.harness/evidence/PREP-03/manifest.json`；跨平台计算方式：

```bash
# Linux / macOS / Git Bash
sha256sum path/to/evidence.png

# Windows PowerShell
(Get-FileHash path/to/evidence.png -Algorithm SHA256).Hash.ToLowerInvariant()
```

## 当前真实状态

Harness 建立不等于产品阶段完成。2026-11-13 初始状态为 0/33；G0 需要真实人工证据，G1 因依赖 G0 尚未解锁，G2 契约待产出。使用 `status` 获取实时结果，不要复制本段数字作为长期状态。
