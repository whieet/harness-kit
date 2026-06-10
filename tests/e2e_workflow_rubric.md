# Harness 工作流符合性评审基准（vs 官方 harness engineering 来源）

本基准把 README「参考来源」5 篇官方文章中的可验证原则逐条映射到 harness-kit 机制与自动证据。
**双重用途**：(1) 人工审阅的对照表；(2) `scripts/dev-e2e.sh` 的 AI 审计输入——评委只依据
`evidence.json` 中的客观证据对每行打分。

**评分规则**：每行 `pass` / `partial` / `fail` / `n-a`，必须附证据指针（测试 ID、trace 事件、
transcript 标记或文件路径）。凡「自动证据」列给出明确证据来源的行，缺证据即 `fail`，不得脑补。

| # | 来源 | 原则 | harness-kit 机制 | 自动证据 |
|---|---|---|---|---|
| O1 | OpenAI Harness Engineering | 入口指令文件是 table of contents，不是百科全书 | `templates/claude-md-template.*` ToC 式章程 + `claude-md-budget` 行数门禁 | `test_init_writes_claude_md`（≤120 行）、`test_claude_md_templates_within_budget`；live SC-1: `claude_md_budget_gate_ran` / SC-2: `budget_gate_ran_in_trace` |
| O2 | OpenAI Harness Engineering | docs/ 是 system of record，知识沉淀成文 | `docs.keyDocs` 注入 + `doc-links`/`doc-gardening` gates + 章程铁律 4 | `test_doc_links_dead`/`test_doc_links_live`；S6（init→verify 含 doc-links）|
| O3 | OpenAI Harness Engineering | progressive disclosure：小而稳的入口 + 指针式导航 | SessionStart 注入紧凑 handoff（git 状态/active plans/advisor/关键文档**指针**，不内联全文） | `test_session_start_emits_json`；live probe/SC-2/SC-6: `handoff_injected`（SC-1 启动时项目未初始化，handoff 静默是 `test_inert_uninitialized` 验证的正确行为） |
| O4 | OpenAI Harness Engineering | 计划与技术债随仓库版本化共置 | plan-approved hook 自动落盘 + `<plan.dir>/{active,completed}` 入库 | `test_plan_approved_writes_file`；S1；live SC-2: `auto-*.md` 落盘 |
| O5 | OpenAI Harness Engineering | 规则靠 linter/结构检查强制，错误信息内嵌修复指引 | `gates[]` + `layeringRules[]`（message 字段即修复指引）由 harness-verify 执行 | `test_verify_passing_and_failing_gates`、`test_check_layering_violation`；S3 |
| A1 | Anthropic harness-design | Generator/Evaluator 分离，禁止自评 | `agents/evaluator.md`（disallowedTools 含全部编辑工具）+ `/harness-kit:evaluate` | `test_evaluator_agent_cannot_edit`；S7（evaluator recipe 在 Stop 时浮出）；live SC-5 |
| A2 | Anthropic harness-design | sprint contract：写码前先约定 Definition of Done | pre-edit plan gate：编辑受管代码前自动补含 DoD 的计划骨架 | `test_pre_edit_scaffolds`；S1；live SC-2: plan 在首次编辑时已含 DoD |
| A3 | Anthropic harness-design | 基于文件的上下文 handoff | `trace.jsonl` + `pre-compact-snapshot.json` + plan 文件 + git | S4；S5（trace 完整性与指标聚合）；live: `.harness/state/trace.jsonl` 非空 |
| E1 | Anthropic effective-harnesses | 规范/清单只翻状态、不可删改 | plan DoD checklist 勾选制 + `harness-check-plan-dod` + 章程铁律 3 | `test_check_plan_dod_flags_archive_needed`；S1（勾选驱动 block/pass）|
| E2 | Anthropic effective-harnesses | 会话启动仪式：快速恢复工作状态 | SessionStart 自动注入 git log/active plans/advisor（替代手工仪式） | `test_session_start_emits_json`；live SC-6: 第二会话 handoff 引用上次 plan |
| E3 | Anthropic effective-harnesses | 收工前必须自我验证，不许「看起来对」 | Stop hook strict 模式 exit 2 物理拦截 + gates 重跑 | S3；live SC-3: 失败 gate 把会话拦回并被修复 |
| L1 | LangChain anatomy | harness 启动时注入记忆文件，模型负责维护 | init 脚手架 CLAUDE.md（create-if-absent，用户/模型后续维护）+ Claude Code 自动加载 | `test_init_keeps_existing_claude_md`（不覆盖用户内容）；live SC-1 |
| L2 | LangChain anatomy | 能力经 skills 渐进披露，避免启动时上下文超载 | 6 个 skills/commands 双载体按需触发；hooks 静默无事不输出 | `test_commands_skills_in_sync`、`test_inert_uninitialized`（未初始化时全静默）|
| D1 | LangChain deep-agents | 动态上下文注入（运行时发现，非静态堆砌） | PreCompact 快照 → UserPromptSubmit **恰好一次**再注入；SessionStart 实时收集 git 状态 | `test_user_prompt_recovery`；S4（dirty 标记恰好一次语义）|
| D2 | LangChain deep-agents | 完成检查清单 middleware 在退出前拦截 agent | Stop hook = 验证门 + plan DoD 自检 + evaluator recipe 提示 | S1/S3（rc=2 拦截语义）；live SC-3 |
| D3 | LangChain deep-agents | 循环/打转检测 | post-edit 阈值预警 + `loop-{sid}.json` + trace-analyze `top_churn` | `test_post_edit_loop_trigger`；S2；live SC-4 |
| X1 | （综合）增量而非一把梭 | plan 步骤表 + progress log + 小步验证工作流（章程 §2） | S1（多步勾选推进）；live SC-2: `progress_log_updated`（软） |

## 审计输出格式

评委输出 JSON 数组，每行一个对象：

```json
[{"id": "O1", "verdict": "pass|partial|fail|n-a", "evidence": "一句话证据指针"}]
```

- `n-a` 仅用于本次 evidence 中确实未覆盖该行的场景（如只跑了 probe 没跑 SC-5 时的 A1）。
- 多评委多数票合成最终 verdict；分歧行标 `disputed`。
