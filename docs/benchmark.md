# 蓝本对照：harness-kit vs man-in-the-mirror

harness-kit 的纪律设计以 **man-in-the-mirror**（MITM，一个 Godot 项目，下同）约两个月的
harness engineering 实践为蓝本。「是否优于蓝本」需要诚实的框架——两边是**不同项目、不同形态**
（项目内自维护的 hook 脚本 vs 可分发的通用插件），直接比较产出结果不成立。本文三段式回答：
①机制对照矩阵（可严格判定）；②两边可提取的数字；③不可比的边界与后续验证路径。

> 本文所有 MITM 侧事实均直接核自其仓库（`.claude/settings.json`、`.claude/trace.log`、
> `scripts-tooling/`、`progress.json`、`docs/QUALITY.md`），非转述。

## 1. 机制对照矩阵

重要前提：**MITM 并不是「手动仪式」**——它的 `.claude/settings.json` 已把核心环节接成项目级
hooks（SessionStart / PreToolUse / PostToolUse×3 / Stop，Stop 门同样 exit 2 物理拦截）。
harness-kit 相对蓝本的本质差异不是「手动 → 自动」，而是**「绑定单一项目的专属脚本 → 配置驱动、
可分发、带质保体系的通用插件」**，外加两类净新增机制。

| 机制 | MITM 蓝本形态（核实） | harness-kit 形态 | 差异本质 |
| --- | --- | --- | --- |
| 会话启动 handoff | SessionStart hook → `session-start.sh`（自动） | SessionStart hook，`docs.keyDocs`/metrics 由 config 驱动 | 项目专属脚本 → 通用配置化 |
| 计划门禁 | PreToolUse hook → `plan-gate.sh`（自动） | pre-edit hook，受管范围由 `plan.codeGlob` 配置 | 同上 |
| 计划落盘 | PostToolUse hook → `on-plan-approved.sh`（自动） | plan-approved hook | 同上 |
| 循环检测 | PostToolUse hook → `loop-detect.sh`（自动） | post-edit hook + per-session `loop-{sid}.json` + `ignoreGlobs` 配置 | 通用化 + 会话隔离计数 |
| 工具调用追踪 | PostToolUse hook → `trace-agent.sh`；`.claude/trace.log` **15,978 条**（tool_call 15,391 / session_start 173 / session_end 420） | post-tool + **tool-failure** 两个 hook；trace 事件谱系扩展（gate / tool_fail / plan_approved / evaluator） | 通用化 + 事件维度扩展 |
| 完成前验证门 | Stop hook → `verify-completion.sh`，exit 2 物理拦截（trace 中 session_end 420 次 ≫ session_start 173 次，正是拦回重试的痕迹） | stop-verify hook，strict / advisory 可配 | 通用化 + 模式可配 |
| 评估 | `evaluate.sh` 把评估判据注入**同一个 agent** 的上下文（自评式，advisory/strict/auto 三模式） | **无编辑权限的独立 evaluator 子代理**（fresh context）+ rubric + 评分写回 trace | 自评判据 → 真正的生成/评估分离 |
| 分层 / 死链 / 计划 DoD / 文档园艺 | `verify.sh` 内写死调用各 `.sh` | `gates[]` 配置化编排，pre-commit / Stop 门 / `/verify` 三处复用同一编排器 | 写死脚本 → config 驱动 |
| advisor / 成熟度阶段 | `harness_advisor.sh`（阶段条件写死在脚本里） | config `phases[]` + `metrics[]` 驱动 | 写死 → 配置化 |
| 失效模式分析 | `trace-analyze.sh`（churn + 失效模式检测 + 可操作建议，含 --json） | harness-trace-analyze（+ gate 通过率、evaluator 维度统计——依赖扩展后的 trace 事件） | 通用化 + 指标面扩展 |
| 上下文压缩存活 | **无**（settings.json 无 PreCompact / UserPromptSubmit hook） | PreCompact 快照 → UserPromptSubmit **恰好一次**再注入 | **净新增** |
| 努力分级 | CLAUDE.md 散文约定（reasoning sandwich） | `effortRouting` 配置化 tier 路由（默认关） | 散文 → 机制 |
| CLAUDE.md 工程章程 | 手写、两个月演化出 120 行 | init 一键脚手架（双语 ToC 模板 + 行预算门禁） | 手工 → 脚手架 |
| 质保体系 | 无测试——hook 脚本改坏只能在实战中发现 | 348 项确定性测试 + 冻结 bash oracle parity + `plugin validate` + live e2e 场景套件 + 3 评委 AI 审计 | **净新增** |

**矩阵结论（可严格判定的部分）**：14 行中 12 行是蓝本已验证机制——其中 6 行在 MITM 已是
hook 自动化，harness-kit 的增量是通用化/配置化/可分发，而非自动化本身；评估一行是「自评 →
分离」的质变；2 行（上下文压缩存活、质保体系）为净新增。每行 harness-kit 形态均有测试证据
（见 [testing.md](./testing.md) 与 [`tests/e2e_workflow_rubric.md`](../tests/e2e_workflow_rubric.md)）。

## 2. 两边可提取的数字

**MITM 两个月实践（截至 2026-06，核自仓库）**：

- completed plans：**61**（`docs/exec-plans/completed/`）
- harness 成熟度：**Phase 5/5**；`progress.json` 记录 **8 个组件**（2 项 `verified` + 6 项 `done`）
- 质量评分：QUALITY.md **9 个已评分域均分 ≈ 88**（另 tests/、性能两域未评分）；Win11 对齐 **18/18**
- trace 数据：`.claude/trace.log` **15,978 条**，但事件只有 tool_call / session_start / session_end 三类——**没有 gate、tool_fail、evaluator 事件**

**harness-kit 在蓝本数据上算不出来的指标**（因 MITM trace 缺少对应事件）：

- 每门 gate 的通过率 / 失败分布（`gate_outcomes`）
- 工具失败率（`tool_fails / tool_calls`）
- evaluator 维度分数分布（rubric 校准依据）
- per-session 文件 churn 文件（MITM 的循环计数不落独立状态文件）

**harness-kit 自身的实测**：live e2e 全 6 场景 16/16 硬断言通过，17 条符合性原则 3 评委一致
pass（产物 `evidence.json` / `audit.json`，见 testing.md）。

## 3. 诚实边界与后续验证路径

**不可直接比较的原因**：

1. **项目不同**——MITM 是 Godot 产品工程（两个月真实开发），harness-kit 的 e2e 跑在沙箱小项目上；「业务成功」定义无法对齐。
2. **形态不同**——项目内脚本可以为 MITM 的路径与 Godot 栈深度定制（MCP 验证集成等），插件必须项目无关；各有所长。
3. **度量口径不同**——两边 trace 事件谱系不同，多数过程指标只有 harness-kit 一侧可算。

因此本文**只主张**：蓝本机制全覆盖 + 通用化/可分发 + 评估质变（自评 → 分离）+ 两项净新增；
**不主张**「产出质量优于蓝本」。

**后续验证路径（MITM 反向迁移）**：在 MITM 仓库跑 `/harness-kit:init godot`，让插件 hooks 接管
项目脚本，运行若干真实开发会话后收集扩展 trace——届时可在**同一项目**上做前后对照（gate 通过率、
churn、计划吞吐），那才是对「优于蓝本」的严格检验。

## 数据来源

- MITM：`.claude/settings.json`（hook 接线）、`.claude/trace.log`（15,978 条事件统计）、`scripts-tooling/`（16 个脚本，含 `evaluate.sh`/`trace-analyze.sh`）、`progress.json`、`docs/QUALITY.md`、`docs/exec-plans/completed/`
- harness-kit：`hooks/hooks.json`、`scripts/harness/`、`tests/`、live e2e 产物（`evidence.json` / `audit.json`）
