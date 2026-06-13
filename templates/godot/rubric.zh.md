# 评估 Rubric — Godot

按当前 active plan 的需求（不是代码自称完成了什么）给每个维度打 **1–5** 分。**任一维度 < 3 = FAIL。** 使用 `.harness/config.json` 里的 `verificationRecipe` 收集证据——实际运行 MCP 工具并阅读完整输出。

## 1. 功能性（硬门）
- 通过你的 Godot MCP server 运行受影响场景：场景能启动且不崩溃。
- 没有运行时/脚本错误（检查 editor-errors 工具）。
- 改动行为确实按计划要求工作（通过输入模拟 / 脚本执行驱动验证）。
- 5 = 包含空/错误状态在内的路径都已验证；3 = 快乐路径已验证；1 = 崩溃或没有证据。

## 2. 视觉 / UX
- 截取受影响场景截图：布局完整且未损坏。
- 如项目维护 screenshot baseline，则对比 baseline：没有非预期回归。
- 新元素符合既有视觉语言（见设计文档，例如 `docs/DESIGN.md`）。
- 5 = 像素一致且符合规格；3 = 可接受但有轻微打磨债；1 = 视觉明显损坏。

## 3. 集成
- 应用既有功能和流程仍可工作。
- autoload signal 接线正确（event bus / registry 模式——通过 node-state / signal assertion 验证）。
- 5 = 无回归且 signal 已验证；3 = 无明显回归；1 = 破坏既有流程。

## 4. 代码质量
- `harness-verify` 退出码为 0（layering + headless compile）。
- 没有硬编码路径、debug 遗留，遵守分层方向。
- 5 = 干净、符合 Godot 惯用法、有必要文档；3 = 可工作但有债；1 = 分层违规或死代码。

## 结论
- PASS = 每个维度 ≥ 3。WARN = 全部 ≥ 3 且有维度 == 3（标记技术债）。FAIL = 任一维度 < 3（列出修复项）。
