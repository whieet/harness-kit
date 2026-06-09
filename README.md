# Harness Kit

[English](README.en.md) | **中文** · 许可证 MIT

> 把任意仓库变成一个自我校验的 **Plan → Build → Verify → Done**（规划 → 构建 → 校验 → 完成）闭环 —— 一个与项目无关的 Claude Code 工装（harness）插件。

---

## 一、介绍

### 从一个根本问题说起

当你让 LLM 写代码时,**模型本身是固定的**。同一个模型,有人用它做出可靠的工程产出,有人却只得到「看起来能跑、实则漏洞百出」的代码。差别往往不在模型,而在**模型周围的一切** —— 它启动时能看到什么上下文、它的每一步动作受什么约束、它宣称「完成」之前要过哪些验证、出错后有没有反馈纠偏。

这「模型周围的一切」就是 **harness(工装 / 挽具)**。LangChain、Anthropic、OpenAI 对它的定义一致:harness 不是模型,而是**围绕模型的上下文管理、约束、验证与反馈回路**。由此得到一个朴素但关键的结论:

> **LLM 辅助开发的产出质量,主要由 harness 决定,而不是模型。**

Harness Kit 就是从这个第一性原理出发的:既然 harness 才是杠杆所在,那就把一套好的 harness 做成可复用的工程产物。

### Harness Kit 是什么

Harness Kit 把一套**可复用、与项目无关**的 harness 打包成 Claude Code 插件。一条 `/harness-kit:init`,就让任意仓库获得一个自我校验的 **Plan → Build → Verify → Done** 闭环:

- 每个会话以 git 状态、活动计划、关键文档作为**交接上下文**启动;
- 编辑未规划的代码会**自动生成计划骨架**;
- 反复编辑同一文件会收到「重新考虑方法」的提示;
- 上下文压缩前后,把「哪个计划没完成、哪个验证没过」**快照下来再注入回去**,让契约穿越压缩;
- 宣称「完成」时,Stop 钩子会跑项目的验证门禁 + 计划 DoD 自检,**过早的「完成」会被挡下来**;
- 需要时,派发一个全新上下文、禁用写权限的**独立评估器**,按 rubric 给改动打分。

### 它解决什么痛点

LLM 辅助开发普遍缺一个**自动、可配置、贯穿全流程**(从会话开始到宣称完成)的工程检查框架。Claude Code 原生提供了 hook 的**事件**与**注入机制**(SessionStart / UserPromptSubmit 的 `additionalContext`、PreToolUse 上下文、Stop 的 `exit 2`、PreCompact、PostToolUse、Setup),但**没有任何具体的内容行为** —— 没有多门禁验证编排、没有循环检测、没有计划持久化、没有上下文快照。Harness Kit 把这些补齐,并全部接到原生事件上。

### 适合谁

用 Claude Code 做开发、希望产出能被**验证**而非「看起来能跑」的个人与团队。开箱自带 **godot** 与 **web** 两套预设,也支持 **custom** 任意项目。

---

## 二、设计哲学

每一条原则,都从开头那个根本命题推导而来,采用 **问题 → 推导 → 落地** 的结构。

### 1. 与项目无关:插件代码零项目字面量
- **问题**:一套 harness 若写死了某个项目的文件路径和命令,就只能服务那一个项目。
- **推导**:harness 要能跨仓库复用,就必须把「项目相关」与「机制」彻底分离。
- **落地**:所有项目相关内容(文件 glob、验证命令、分层规则、能力开关)都集中在每个项目唯一的 `.harness/config.json`;插件代码本身不含任何项目字面量,运行时也不对项目类型做分支。

### 2. 未初始化即惰性:安装零副作用
- **问题**:一个装上就改变行为的插件,会让人不敢装。
- **推导**:安装这一步本身不应有任何副作用。
- **落地**:没有 `.harness/config.json` 时,每个 hook 都是空操作(`exit 0`)。在未初始化的仓库装上 Harness Kit,什么都不会变。

### 3. 能力由你掌控,而非自动路由
- **问题**:一个「聪明」的自动路由器会替你决定何时收紧、何时放松验证,但它的判断未必对,而且不透明。
- **推导**:harness 是脚手架,会随项目成熟而演进、最终被拆除 —— 这个节奏应由人掌握。
- **落地**:`enabledCapabilities{}` 是一组**你拥有的开关**(`planGate`、`loopDetection`、`toolTrace`、`evaluator`、`contextSnapshot`,以及实验性的 `evaluatorAutoDispatch`)。你直接开关;工具只**建议**,绝不替你**强制**。

### 4. 「完成」是一道门,不是一句声明
- **问题**:LLM 很容易宣称「我做完了」,而实际上测试没过、计划的验收项没勾。
- **推导**:「done」必须被**挣得**,而不是被**声明**。
- **落地**:Stop 钩子在每次宣称完成时,跑配置里的阻塞门禁 + 检查活动计划的 DoD;`strict` 模式下任一项不过就 `exit 2`,挡住这次「完成」。(这就是俗称的 "Ralph Loop"。)

### 5. 生成者与评估者分离
- **问题**:让写代码的人给自己的代码打分,既有偏向、又容易自我合理化。
- **推导**:评判者不该是产出者。
- **落地**:评估器是一个**独立子代理** —— 全新上下文、禁用 Write/Edit,只能按 rubric 打分和给建议、不能动手修。任一维度 <3 即判 FAIL。

### 6. 契约必须穿越上下文压缩
- **问题**:长会话会触发上下文压缩(compaction),压缩后「还有哪个计划没做完、哪个门禁失败」很容易丢失。
- **推导**:这些是必须延续的契约,不能因压缩而蒸发。
- **落地**:`PreCompact` 把当前计划 / 未勾 DoD / 失败门禁快照到 `.harness/state/`;压缩后下一次 `UserPromptSubmit`(以及 resume 时的 `SessionStart`)再注入一次。(PostCompact 注入不被官方支持,所以这是文档支持的路径。)

### 7. 跨平台:单一内核 + 极薄启动器
- **问题**:逻辑若散落在各平台的 shell 脚本里,既难测试又难移植。
- **推导**:逻辑应集中在一处、可单元测试、可跨平台。
- **落地**:所有 `bin/harness-*` 与 `scripts/run-hook` 都是极薄的 Bash 启动器,只负责定位 Python 解释器并转发;真正的逻辑全在单一 Python 核心(`scripts/harness/`),同一份代码原生跑 macOS / Linux / Windows(含 UTF-8 强制、跨平台进程检查)。

### 8. 基于 trace 的自调,且只建议不强制
- **问题**:一个门禁配久了可能早已无用,却没人发现。
- **推导**:优化应基于**证据**,且尊重用户的最终判断。
- **落地**:每次门禁 / 评估器执行都记进 `trace.jsonl`;`/harness-kit:trace-analyze` 据此分析(如「门禁 X 近 10 次 0 命中,考虑关掉」)并给出建议 —— 改不改,由你决定。

> 一句话总结这套哲学:**harness 是脚手架,项目成熟后该拆;所以能力是你拥有的开关,而不是替你做主的自动路由器。**

---

## 三、使用说明

### 系统要求

| 平台 | 必需 |
|---|---|
| **macOS / Linux** | `python3`(≥3.9)与 `git`,通常系统自带。 |
| **Windows** | [Git for Windows](https://gitforwindows.org/)(提供 `git` + Git Bash)与 [Python 3](https://www.python.org/downloads/windows/)(≥3.9,确保 `python` 或 `py -3` 在 PATH 上)。Claude Code 在 Windows 用 Git Bash 跑 hook,**无需 WSL**。 |

> CI 矩阵在 macOS / Ubuntu / Windows × Python 3.9 与 3.12 上实测通过。

### 安装

```
/plugin marketplace add whieet/harness-kit
/plugin install harness-kit@harness-kit
```

### 初始化

```
/harness-kit:init [godot|web|custom]
```

检测或询问项目类型 → 生成 `.harness/config.json` + rubric + 计划/文档骨架 → 启用 git pre-commit 门禁。幂等;`--force` 重置。初始化之前,插件完全惰性。

### 生命周期:harness 接到哪些事件

| Claude Code 事件 | Harness 行为 |
|---|---|
| **SessionStart** | 注入交接:git 状态、活动计划、已启用能力、关键文档。 |
| **PreToolUse**(Edit / Write) | 计划门禁:编辑匹配 `plan.codeGlob` 的文件且无计划时,自动生成计划骨架。 |
| **PostToolUse**(ExitPlanMode) | 计划批准后持久化为活动计划。 |
| **PostToolUse**(Edit) | 循环检测:同一文件编辑达阈值时,提示「重新考虑方法」。 |
| **PreCompact** | 快照当前计划 / 未勾 DoD / 失败门禁到 `.harness/state/`。 |
| **UserPromptSubmit** | 压缩后重注入一次快照。 |
| **Stop** | 预完成验证门禁:跑阻塞门禁 + 检查 DoD;`strict` 失败则 `exit 2` 挡下「完成」。 |

### 命令一览

| 命令 | 作用 |
|---|---|
| `/harness-kit:init [godot\|web\|custom]` | 检测/询问项目类型,生成配置 + rubric + 骨架,启用 git 门禁。 |
| `/harness-kit:plan` | 进入 plan 模式,以项目计划模板为初始内容。 |
| `/harness-kit:verify` | 跑配置驱动的门禁编排器,逐项报告通过/失败。 |
| `/harness-kit:evaluate` | 派发独立评估器子代理,按 rubric 给当前改动打分(任一维度 <3 = FAIL)。 |
| `/harness-kit:advisor` | 被动面板:产物计数、已启用能力、配置门禁、trace 建议。 |
| `/harness-kit:trace-analyze` | 分析 harness 自身 trace,给出门禁 / 配置调优建议。 |

> 另:`claude -p --maintenance` 运行 `harness-maintenance`,迁移旧配置(`phases[]` → `enabledCapabilities{}`)、修复 state。

### 配置:`.harness/config.json`

插件代码零项目字面量,所有项目相关内容都集中在这一个 git 追踪的文件。关键字段:

- `gates[]` —— 验证门禁(名称、命令、阻塞 / tier、跳过条件)
- `layeringRules[]` —— 架构分层规则(scope glob、禁用 regex、补救建议)
- `plan` —— 计划约定(目录、`codeGlob`、状态字段、DoD 正则)
- `docs` —— 关键文档、扫描根、架构漂移检查
- `metrics[]` —— 产物计数(文档、已完成计划等)
- `enabledCapabilities{}` —— 能力开关(见设计哲学第 3 条)
- `effortRouting` —— 可选的推理三明治:低 / 中 effort 仅跑 `tier:"fast"` 门禁(跳过会被记录,绝不静默),高+ effort 跑全部;**默认关**
- `evaluator` / `verificationRecipe` —— 评估器 rubric 路径与「维度 → 检查」映射
- `verificationMode` —— `advisory`(仅告警)或 `strict`(`exit 2` 阻断)

完整 schema 见 `templates/config.schema.json`;`templates/godot/` 与 `templates/web/` 的预设是理解真实配置最快的途径。

### 项目结构速览

```
scripts/harness/      Python 核心(hooks/ 与 commands/ 的全部逻辑)
scripts/run-hook      bash hook 启动器(定位 Python 并转发)
bin/harness-*         极薄 bash 命令启动器
hooks/hooks.json      Claude Code hook 事件声明
templates/            config schema、计划模板、godot / web 预设
skills/               6 个斜杠命令前端(init / plan / verify / evaluate / advisor / trace-analyze)
agents/evaluator.md   独立评估器子代理定义
```

---

## 迁移已有的手写 harness

装插件 → `/harness-kit:init <type>` 生成等价 `.harness/config.json` → 在一个已知干净、一个已知脏的提交上确认 `/harness-kit:verify` 复现旧门禁结果 → 删旧脚本、从 `.claude/settings.json` 移除 `hooks` 块。已在用旧版 Harness Kit 配置?运行 `claude -p --maintenance` 把 `phases[]` 迁移成 `enabledCapabilities{}`。

## 可选组合件(非依赖)

Harness Kit **自包含**。以下 marketplace 插件可*补充*它,但不取代其核心:**claude-mem**(跨会话持久记忆)、**code-review**(官方,push 前 diff 评审)、**security-guidance**(官方,安全扫描)。

## 许可证

MIT —— 见 `LICENSE`。
