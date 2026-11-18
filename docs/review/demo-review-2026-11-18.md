# Demo 全面审查报告（2026-11-18）

> 审查对象：`origin/main` 分支提交 `d801076` 中的 `demo/统一消息管理_初赛提交/`（42 个文件，约 3000 行代码）
> 审查依据：AGENTS.md、`.harness/feature_list.json`（33 任务）、`.harness/gates.json`、`docs/需求分析文档.md` v1.1、赛题 A 原文
> 审查方法：harness 启动仪式（doctor/validate/status/ci 全通过）→ 逐文件通读全部源码 → 40 个单测实跑 → 本机冒烟测试（启动/登录/接口/webhook）→ 密钥泄露扫描 → git 分支拓扑与证据链核查

---

## 一、总体结论

**Demo 作为初赛提交物本身质量良好；但按 harness 工程标准判定不合格，不能进入 harness 意义上的后续交付或验收。**

- 代码质量：分层清晰（app / config / core / adapters / web / tests），注释与设计理由充分，异常分支普遍有处理；40 个单元测试全部实跑通过（`Ran 40 tests, OK`）；本机冒烟测试启动、登录、鉴权、消息接口、SSE 均正常。
- 工程纪律：**demo 完全游离于 harness 任务体系之外**——0/33 任务通过，IM-01～IM-06 全部 blocked 且无 verify 记录；demo 提交 `d801076` 直接推送 `main`，绕过了 AGENTS.md 规定的任务认领、验证与证据归档流程，且 `main` 分支目前没有 CODEOWNERS、没有 CI workflow，外部信任锚不成立。
- 诚实度：demo 的 README/验证记录对未验证项（飞书接收、文件发送、Docker 构建等）如实披露，无虚构证据迹象（AGENTS.md 红线未违反）。

**验收判定：不可进入 G3/G4 交付。** 阻塞项见 P0 清单。

---

## 二、问题清单（按严重程度）

### P0 — 阻塞验收，必须整改

#### 1.【流程/harness】demo 绕过 harness 工作流直接提交并推送 main
- **模块**：git 历史 / `.harness/feature_list.json`
- **证据**：`git log origin/main` 显示 `d801076 "feat: add demo module from initial-round submission"`；harness `status` 显示 0/33 任务通过，IM-01～IM-06 全部 `blocked`、`verification.ready=false`；`.harness/evidence/` 下没有任何 IM 任务的验证记录；工作区日志（demo/.workbuddy/memory/2026-11-18.md）描述的修复（单测环境依赖、README 测试数 31→40）发生在 harness 体系之外。
- **影响**：AGENTS.md §4 规定 `passes` 只能由 `harness.py verify` 修改、证据必须 SHA-256 归档；demo 的存在使"任务状态 0/33"与"功能已大量实现"两个事实矛盾，CI 的 `history` 检查与门禁结论全部失真。
- **整改建议**：将 demo 代码按 IM-01～IM-06 的边界拆分认领；为每个任务补齐 `verification`（文件、命令、阈值）后运行 `harness.py verify <TASK_ID>` 归档证据；PREP-03 的钉钉真实收发截图从 `demo/docs/assets/verify/` 复制归档到 `.harness/evidence/PREP-03/` 并经人工批准。
- **优先级**：P0

#### 2.【流程/信任锚】main 与 harness/bootstrap 分叉，main 缺少外部信任锚
- **模块**：git 分支拓扑、`.github/`
- **证据**：`merge-base = 87d0f83`；`origin/main` = 初始化 → d801076（含 demo，**无** .github、AGENTS.md、.harness）；`origin/harness/bootstrap` = 初始化 → 1d8713a → 0fb35d8（含 harness，**无** demo）。`git ls-tree origin/main` 顶层只有 .gitignore/README/demo/docs，无 `.github/CODEOWNERS`、无 CI workflow。
- **影响**：AGENTS.md §4 的外部信任锚（CODEOWNERS + main 分支保护 + 必需状态检查）在 main 上完全不成立——事实上 d801076 就是被直接 push 到 main 的。任何人后续直推 main 即可绕过全部门禁。
- **整改建议**：① 将 harness/bootstrap 合并回 main（或反之），使 main 同时包含 harness 与 demo；② 在 GitHub 为 main 启用强制 PR + CODEOWNERS + harness 必需状态检查；③ 合并前运行 `harness.py ci` 与 `history` 校验确认证据链不断裂。
- **优先级**：P0

#### 3.【需求一致性】需求基线双份漂移，两套文档体系并存
- **模块**：`docs/`（根）与 `demo/统一消息管理_初赛提交/docs/`
- **证据**：两份《需求分析文档.md》同为 v1.1 但编制者不同（根：RA-Agent；demo：项目组），内容近似存在细节差异（MD5 不同：`ed4c35…` vs `4d1124…`）；demo 自带完整 docs 体系（index.md、architecture.md、接入指南、验证记录），与根目录 `contracts/`、`docs/design/`（目前仅 README 占位）构成两套并行事实源。
- **影响**：违反 AGENTS.md §2 唯一事实源原则；G2 契约（DS-01～DS-06 计划的 ADR、JSON Schema、OpenAPI、DDL）尚未产出，而 demo 已按自己的设计实现，后续契约正式化时必然冲突。
- **整改建议**：以根目录 docs 为基线，demo/docs 定位改为"提交物快照"并在根 README 声明从属关系；DS-01～DS-05 契约按 demo 现状补齐（含 SSE 替代 WebSocket 的 ADR 决策记录），而不是让两套文档各自演化。
- **优先级**：P0

### P1 — 初赛提交前应修复

#### 4.【流程/证据】钉钉真实收发证据未进入 harness 证据体系
- **模块**：`demo/docs/assets/verify/`（4 张截图）、`.harness/evidence/`
- **证据**：PREP-03（"至少一个平台真实收发连通证据"，human_required）仍为 blocked；验证截图与 `/healthz` 返回原文都在 demo/docs 内，未归档到 `.harness/evidence/PREP-03/`。
- **影响**：初赛材料中"平台收发验证"的证据链与 harness 脱节；人工批准人记录缺失。
- **整改建议**：执行 `harness.py verify PREP-03 --human-approved-by "真实姓名"`，证据文件复制归档并计算 SHA-256。
- **优先级**：P1

#### 5.【代码/健壮性】两处未捕获异常导致接口 500
- **模块**：`app.py`（api_mock_seed、api_mock_push）
- **证据**：冒烟实测——`POST /api/mock/seed {"count":"abc"}` → 500（`int(data.get("count", 5))` 无 try/except）；`api_mock_push` 传未知 platform（如 wecom）时 `service.receive` 抛 `ReceiveError` → 500（该端点无 try/except）。对照同文件 `api_messages` 对 limit 已做防御，风格不一致。
- **影响**：演示现场参数误传即 500；违背"参数写错了不能让接口 500"的既定自守标准（代码注释自述）。
- **整改建议**：`count` 解析复用 limit 的防御模式；`api_mock_push`/`api_mock_duplicate` 捕获 `ReceiveError` 返回 400 并附 stage/reason。
- **优先级**：P1

#### 6.【部署】Docker 未在干净 Linux 环境验证，依赖版本浮动
- **模块**：`Dockerfile`、`requirements.txt`
- **证据**：demo README"已知限制"自述"还没在干净 Linux 环境实际构建验证过"；`requirements.txt` 用 `Flask>=3.1.0`、`dingtalk-stream>=0.24.0` 浮动版本，构建不可复现。对应 DP-01/DP-02（blocked）与 NFR-08。
- **影响**：决赛"纯净环境一键启动"目标（需求 NFR-08：演练 ≥2 次）当前无证据支撑。
- **整改建议**：初赛后立即执行 DP-01/DP-02 流程；requirements 锁定具体版本（至少补 constraints 文件）；本机 Docker 29.5.2 可先做一次本地构建演练。
- **优先级**：P1

### P2 — 决赛前应修复

#### 7.【需求一致性】NFR-02 部分未实现：401/403 即时刷新与在途请求排队重发
- **模块**：`adapters/feishu.py`、`adapters/dingtalk.py`
- **证据**：`_get_token` 只实现"剩余有效期 < 300s 主动刷新"（对应需求前半句）；未实现收到 401/403 即时刷新、刷新期间在途请求排队并在新 token 就绪后重发（需求验收标准明确要求构造失效验证重发成功）。
- **影响**：长时运行后 token 失效窗口内发送会失败并进入重试/死信链路。
- **整改建议**：在 `_post/_post_json` 返回 401/403 时强制置空缓存 token 并重试一次。
- **优先级**：P2

#### 8.【需求一致性】待办聚合与 DS-04 规划表结构未落地
- **模块**：`core/store.py`、需求 FR（待办聚合 Should 级）
- **证据**：库表仅 `messages`/`traces` 两张；DS-04 DoD 要求覆盖 `conversations`、`platform_accounts`、`todo_items`、`sync_status`；schema.py 支持 `todo` 消息类型但 service/前端无待办视图。IM-06（状态回流与待办聚合）为 blocked。
- **影响**：需求范围 Should 级缺失；DS-04 契约正式化时需要决策"按 demo 现状收缩"还是"补齐表结构"。
- **整改建议**：初赛按现状交付（Must 级闭环已覆盖），决赛前将 DS-04 契约与实现对齐（二选一，写 ADR）。
- **优先级**：P2

#### 9.【安全】mock 模式下 webhook 对任意未签名流量放行并入库
- **模块**：`app.py`（/webhook）、`adapters/feishu.py`/`dingtalk.py`（verify 在 MODE=mock 时直接 True）
- **证据**：冒烟实测——`POST /webhook/dingtalk {}`（无任何签名头）→ `200 {"code":0,"msg":"ok"}`，消息成功入库。
- **影响**：mock 模式端口一旦暴露（Docker 默认绑 0.0.0.0），任何人可无限制灌库（parse_failed 分支也不设上限）；配合 auto_push 可形成资源消耗。
- **整改建议**：mock 模式下 webhook 增加 `UMM_ALLOW_UNSIGNED_WEBHOOK=1` 显式开关（默认关）；或对 webhook 来源做本地回环限制；同时给 parse_failed 消息量加上限。
- **优先级**：P2

#### 10.【需求一致性】SSE 替代 WebSocket、HTTPS 缺失未在根文档记录
- **模块**：`core/bus.py`、需求 NFR-05（"≥50 并发 WebSocket 会话"）/ NFR-12（HTTPS）
- **证据**：bus.py 注释解释了选 SSE 的理由（合理），但 NFR-05 验收标准（50 并发会话压测）从未执行；NFR-12 HTTPS 完全未提及（部署层可由前置代理解决但无方案说明，需求文档 Q-06 有预案引用）。
- **影响**：决赛答辩时 NFR 追溯矩阵出现空口承诺。
- **整改建议**：DS-05 契约落地时正式决策 SSE/WebSocket 并改写 NFR-05 表述；部署指南补 HTTPS 方案（nginx 反代）。
- **优先级**：P2

#### 11.【运维/一致性】进度叙事分裂
- **模块**：根 `README.md`、`.harness/progress.md`、demo `README.md`
- **证据**：根 README（harness/bootstrap）："当前不是产品完成态…0/33"；demo README：大量功能已实测打通。progress.md"当前交接"停留在 2026-11-13 harness bootstrap，未反映 demo 已入 main。
- **影响**：任何 Agent 按启动仪式进入仓库都会得到与实际不符的基线判断。
- **整改建议**：合并分支后统一更新 progress.md"当前交接"，写明 demo 的真实状态与唯一下一步动作。
- **优先级**：P2

### P3 — 低风险，择机修复

12. **飞书 token 比对用 `==`**（feishu.py verify），非常量时间比较；钉钉已用 `hmac.compare_digest`，建议对齐。理论时序侧信道，实际风险低。
13. **错误响应回传 `str(e)`**（app.py display/process/reply/confirm 四处 `except Exception as e: ... str(e)`），KeyError 内容含内部 ID，建议映射为固定文案+日志留详情。
14. **Flask 开发服务器作 Docker CMD**（`app.run(threaded=True)`）：每 SSE 连接一线程、无并发上限、无生产 WSGI。演示可接受，决赛部署建议换 waitress/gunicorn（Windows 兼容性注意）。
15. **回调重放窗口 1 小时**（`CALLBACK_MAX_SKEW_SECONDS=3600`）：钉钉验签时间偏差容忍过大，建议收紧到 300～600s 并说明依据。
16. **requirements.txt 把可选依赖 dingtalk-stream 列为必装**：与"不装也能跑"的设计意图不完全一致（单测确实不依赖，但纯净环境安装体积与故障面变大）；建议拆为 extras 或注释说明。
17. **个人信息**：`docs/钉钉接入指南.md`、`验证记录.md` 含真实 userId `023519171132751217` 与真人姓名，对外提交前建议脱敏（密钥扫描确认无真实 secret，`SECxxxx…` 为占位符）。
18. **中文目录名 `demo/统一消息管理_初赛提交/`**：跨平台脚本/CI 存在编码风险（.gitattributes 已配置缓解），且与 IM-01 脚手架布局预期不符，整合时建议评估迁移为 ASCII 路径。

---

## 三、需求覆盖矩阵（摘要）

| 需求项 | 状态 | 说明 |
|---|---|---|
| 闭环：接收→展示→处理→回复→状态回流 | ✅ 完整 | mock 全链路 + 状态机强制 + traces 留痕 |
| 幂等去重（NFR-03/US-06） | ✅ | event_id UNIQUE + IntegrityError 转 return |
| 429 指数退避 5 次（NFR-01） | ✅ | 含可注入故障演示 |
| Token 提前刷新（NFR-02 前半） | ✅ | 300s 阈值，双 token 各自缓存 |
| 登录 + 30min 空闲超时（NFR-13） | ✅/△ | 会话控制完整；口令明文 env（已声明 demo 限制） |
| 钉钉真实收发 | ✅ | Stream 长连接入站 + 机器人单聊出站，有截图/接口原文 |
| 飞书真实收发 | △ 仅发送 | 群 Webhook 出站实测；接收被公网/租户策略阻塞（如实披露） |
| 待办聚合（Should） | ❌ | 未实现 |
| NFR-02 后半（401/403 即时刷新+排队重发） | ❌ | 未实现 |
| NFR-05（WebSocket 50 并发压测） | △ | 改用 SSE，无压测证据 |
| NFR-08（纯净 Linux 部署 ≥2 次） | ❌ | Dockerfile 写好未验证（自述） |
| 企业微信/AI 摘要（Could） | ❌ | 未实现（符合 MoSCoW 取舍） |

---

## 四、整改路线建议

1. **立即（P0）**：合并 `harness/bootstrap` 与 `main`（保留双方内容）→ 在 GitHub 配置 main 分支保护 + CODEOWNERS + CI 必需检查 → 更新 progress.md 交接。
2. **初赛前（P1，截止 11/20）**：PREP-03 证据归档 + 人工批准；修复两处 500；确认初赛提交包（QA-04 人工核查）。
3. **初赛后（P2）**：把 demo 映射进 IM-01～IM-06 任务并逐个 verify；DS-01～DS-05 契约按实际实现补齐（含 SSE/SQLite 取舍 ADR）；修 NFR-02 与 mock webhook 开关；Docker 干净环境演练两次（DP-01/DP-02）。
4. **决赛前（P3）**：安全细节、生产 WSGI、待办聚合取舍。

---

## 五、审查执行记录

- harness：`doctor` ✓、`validate` ✓、`status`（0/33）✓、`ci` ✓；G2 证据如实为 `passed: False`。
- 单测：`python -m unittest discover -s tests` → `Ran 40 tests in 0.834s, OK`（与工作日志声明一致）。
- 冒烟：healthz/登录/401 鉴权/消息列表/飞书 url_verification challenge ✓；发现 2 处 500 与 mock webhook 开放灌库问题（见 #5、#9）。
- 密钥扫描：无真实密钥；`SECxxxx` 为占位符；发现真实 userId/姓名属个人信息（见 #17）。
- git：分叉拓扑、reflog、双分支内容核查（见 #1、#2、#3）。
