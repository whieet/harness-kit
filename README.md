# Harness Kit

[English](README.en.md) | **中文**

一个**与项目无关的 Claude Code 工程化（harness-engineering）插件**。它把任意
仓库变成一个自我校验的 **Plan → Build → Verify → Done**（规划 → 构建 → 校验 → 完成）闭环：

- **会话交接（Session handoff）** —— 每个会话启动时注入 git 状态、活动计划、已启用能力、关键文档。
- **计划门禁（Plan-gating）** —— 编辑未规划的代码会自动生成计划骨架；批准计划（ExitPlanMode）时持久化。
- **完成前校验门禁** —— Stop hook 跑项目校验门禁 + 计划 DoD 自检，阻止过早宣称“完成”（exit 2）。
- **独立评估器** —— `/harness-kit:evaluate` 派发一个怀疑论、全新上下文的子代理，按 rubric 给改动打分（Generator/Evaluator 分离）。
- **循环检测** —— 对同一文件反复编辑注入“重新考虑方法”的提示。
- **上下文管理** —— compaction 前快照“哪个计划/哪些未勾 DoD/哪个门禁失败”，之后再注入一次，让契约穿越压缩。
- **trace 驱动自调** —— 不再用成熟度阶段自动路由器，而是分析自己的 trace 并**建议**配置改动（“gate X 近10次0命中，考虑关掉”），由你决定。

所有与项目相关的内容（文件 glob、校验命令、分层规则、校验方式、能力开关）
都集中在每个项目唯一的 **`.harness/config.json`** —— 插件代码本身
**不含任何项目字面量**。开箱即带两套预设：**godot** 和 **web**。

> 设计依据：harness engineering（LangChain / Anthropic / OpenAI 的定义）——
> harness 即“模型周围的一切”。一条核心原则是*“harness 会演进——项目成熟后拆掉脚手架”*，
> 所以能力开关是用户拥有的配置，而非自动路由器。

## 为什么做成插件（哪些原生、哪些插件捆绑）

Claude Code 原生提供 hook **事件**与**注入机制**（SessionStart / UserPromptSubmit
的 `additionalContext`、PreToolUse 上下文、Stop 的 `exit 2` / `decision:block`、
PreCompact、PostToolUse、Setup）—— 但**不含** harness 所需的任何**内容行为**：
没有多门禁校验编排器、没有按文件循环检测、没有计划持久化/脚手架、没有文档漂移审计、
没有上下文快照。Harness Kit 通过这些原生事件把它们补齐。（每个机制都对照官方 hooks
文档核实；例如 `type:agent` 钩子是实验性的且**仅上下文、无法阻断**，所以阻断门禁始终
是 `type:command` 的 Stop 钩子。）

## 安装

```
/plugin marketplace add river/harness-kit
/plugin install harness-kit@harness-kit
/harness-kit:init           # 检测 godot|web，或询问；生成 .harness/config.json
```

插件在**初始化之前处于惰性** —— 没有 `.harness/config.json` 时每个 hook 都是空操作，
在未初始化的仓库上安装不会带来任何改变。

## 命令

| 命令 | 作用 |
|---|---|
| `/harness-kit:init [godot\|web\|custom]` | 检测/询问项目类型，生成 `.harness/config.json` + rubric + plan/docs 骨架，启用 git pre-commit 门禁。幂等；`--force` 重置。 |
| `/harness-kit:verify` | 运行配置驱动的门禁编排器，逐项报告通过/失败。 |
| `/harness-kit:evaluate` | 派发怀疑论 evaluator 子代理，按 rubric 给当前改动打分（任一维度 <3 = FAIL）。 |
| `/harness-kit:advisor` | 被动面板：产物计数、已启用能力、配置的门禁，以及 trace 驱动的建议。 |
| `/harness-kit:plan` | 进入 plan 模式，以项目计划模板作为初始内容。 |
| `/harness-kit:trace-analyze` | 分析 harness 自己的 trace：重复工具循环、churn、延迟校验、门禁/评估器校准。 |

另：`claude -p --maintenance` 会运行 `harness-maintenance`（迁移旧配置、修复 state）。

## 能力开关、effort 路由、上下文管理

- **`enabledCapabilities{}`** —— 用户拥有的开/关（`planGate`、`loopDetection`、`toolTrace`、`evaluator`、`contextSnapshot`，以及实验性的 `evaluatorAutoDispatch`）。取代旧的成熟度阶段自动路由器。你直接开关；trace 建议器只建议、你决定。
- **`effortRouting`** —— 可选的推理三明治。开启时，低/中 effort 的回合只跑 `tier:"fast"` 门禁（跳过项会被记录、绝不静默）；高+ effort 跑全部。**默认关**，避免低 effort 回合悄悄削弱验证。
- **上下文快照** —— `PreCompact` 写 `.harness/state/pre-compact-snapshot.json`；下一次 `UserPromptSubmit` 重注入一次（PostCompact 注入不被支持，这是文档支持的路径）；`SessionStart` 在 resume 时也会呈现。
- **实验性自动评估** —— `hooks/optional-auto-eval.json` 是可选的 `type:agent` Stop 钩子，自动跑 evaluator。它**仅上下文、无法阻断**、每次 Stop 都跑、**默认关**。日常用 `/harness-kit:evaluate`。

## 可选组合件（非依赖）

Harness Kit **自包含**。以下 marketplace 插件可*补充*它，但不取代其核心（已核实：
它们都没有实现 Harness Kit 拥有的 Stop-hook 门禁 / 能力模型 / 计划生命周期）：

- **claude-mem** —— 持久的跨会话记忆（Harness Kit 的交接是轻量的单会话诊断）。
- **code-review**（官方）—— `/code-review` 作为附加的 push 前 diff 评审；斜杠触发、面向 PR，*不是* Stop-hook 门禁。
- **security-guidance**（官方）—— 三层安全扫描，在需要安全门禁处加上。

## 配置

完整键参考见 `templates/config.schema.json`。`templates/godot/` 和 `templates/web/`
的预设是理解真实配置最快的途径。

## 迁移已有的手写 harness

安装插件 → `/harness-kit:init <type>` 生成等价 `.harness/config.json` → 在一个已知干净
和一个已知脏的提交上确认 `/harness-kit:verify` 复现旧门禁结果 → 删旧脚本、从
`.claude/settings.json` 移除 `hooks` 块。已经在用旧版 Harness Kit 配置？运行
`claude -p --maintenance` 把 `phases[]` 迁移成 `enabledCapabilities{}`。

## 许可证

MIT —— 见 `LICENSE`。
