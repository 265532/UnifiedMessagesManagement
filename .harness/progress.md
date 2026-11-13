# Harness 进度与交接

> 本文件只记录导航信息。唯一任务状态见 `feature_list.json`；唯一验收结论见验证命令与 evidence。

## 当前交接（2026-11-13）

- 当前分支：`harness/bootstrap`
- 当前主任务：工具无关 Harness 已建立并完成自检；这不是产品功能完成。
- 实测基线：26 个 Harness 单元测试、`validate`、`ci`、`history HEAD^ HEAD` 通过；`gate G2` 如实失败并归档到 `.harness/evidence/G2/result.json`；任务状态 0/33。
- 唯一推荐下一动作：先由真实人工处理 `PREP-01`（赛题确认），同时补齐 `PREP-02` 账号 Checklist；随后按依赖推进 G1 与 G2 契约，不要并行启动产品实现。
- 外部动作：仓库维护者需在 GitHub 为 `main` 启用 CODEOWNERS 强制评审与 `harness` 必需状态检查；本地无法代替该分支保护。
- 风险：飞书/钉钉账号权限是外部依赖；11/20 初赛硬截止不变。
- 禁止：把 Harness 文件创建成功表述为 G0/G1/G2 已通过。

## 历史摘要

### 2026-11-13 · Harness bootstrap

- 新增仓库内角色、任务、门禁、报告 Schema、DSH 适配和本地/CI 验证入口。
- 原 `docs/index.md` 保留为管理基线；执行日期以 `execution-plan.json` 为准。
- 修正原依赖中 IM-03 → IM-04 的非必要串行；两者在核心与账号条件满足后可并行。
- 原 Phase 5 重复任务编号 `IM-07*` 规范为 `ENH-01`。
- 加入独立任务/门禁证据、SHA-256 指针、Git 历史状态锚点与 CODEOWNERS 外部信任边界。

## 会话结束检查单

1. 工作区只包含本任务相关改动，失败证据未删除。
2. 已运行必要验证，命令与退出码已写入报告。
3. 若任务通过，必须能看到对应 `last_verification`；否则不得声称完成。
4. 更新本文件的“当前交接”，写清唯一下一动作与阻塞。
5. 提交 Git；提交哈希写入会话交接模板或 Agent 报告。
