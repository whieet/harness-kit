{{IMPORTS}}# CLAUDE.md — 项目章程

> 由 harness-kit 为 {{PROJECT_TYPE}} 项目生成。本文件是目录而非百科全书——保持在
> {{LINE_BUDGET}} 行以内（由 `claude-md-budget` 门禁强制）。持久知识沉到 `docs/`，不要堆在这里。

## 1. 铁律

1. **非平凡改动先有计划** —— `{{PLAN_DIR}}/active/` 须有覆盖计划（从 `{{PLAN_DIR}}/_template.md` 起一份，或由计划门禁自动补骨架）。
2. **`harness-verify` 非 0 退出不得宣布完成** —— 它跑 `.harness/config.json` 里的全部门禁，同时是 pre-commit 钩子和 Stop 门。
3. **验证门与测试不可删除或削弱** —— 可新增、可带书面理由跳过；绝不为了过检而改掉失败的检查。
4. **知识沉到 `docs/`** —— 没写下来的约定对 agent 等同不存在。
5. **遵守 `layeringRules` 声明的依赖方向**（`.harness/config.json`）。

## 2. 标准工作流 —— Plan → Build → Verify → Done

| 步骤 | 内容 | 产物 |
|---|---|---|
| Plan | 复制 `{{PLAN_DIR}}/_template.md` 到 `active/`，填背景/目标/步骤/完成判据 | plan 文件 |
| Build | 按计划增量实现，遵守分层规则 | 代码 |
| Verify | 跑 `harness-verify` + 运行时验证；结果写回 plan 进度日志，勾选完成判据 | 全绿 |
| Done | plan 移入 `{{PLAN_DIR}}/completed/` | 归档 |

> 推理预算花在 Plan 和 Verify，Build 可以省；小步推进、每步验证。

## 3. 仓库地图

| 需求 | 路径 |
|---|---|
| 当前任务 | `{{PLAN_DIR}}/active/` |
| 起新 plan | `{{PLAN_DIR}}/_template.md` |
| Harness 配置（门禁/分层/计划规则） | `.harness/config.json` |
| 评估 rubric | `.harness/rubric.md` |
| 架构 | (fill in: 架构文档路径，如 `ARCHITECTURE.md`) |
| 设计 / 产品文档 | (fill in: 路径，或删除本行) |

## 4. 验证 SOP

- `harness-verify` —— 本地闸门；同时接入 git pre-commit 与 Stop 门。
- 各维度的运行时验证配方见 `.harness/config.json` 的 `verificationRecipe`。
- 大改动跑 `/harness-kit:evaluate`，按 `.harness/rubric.md` 独立评分。

## 5. 项目事实

- 构建 / 运行：(fill in: 命令)
- 测试：(fill in: 命令)
- 技术栈：(fill in: 框架 + 版本、值得固定下来的环境差异)

<!-- harness-kit:claude-md v1 -->
