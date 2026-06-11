# 测试与评估体系

[English](./testing.en.md) · **简体中文**

harness-kit 的验证不靠「手动建目录 → 开 Claude → 装插件 → 试一遍」。四层金字塔，每层一条命令：

| 层 | 内容 | 调用 Claude？ | 何时跑 |
| --- | --- | --- | --- |
| **L1 单元/奇偶** | smoke、parity（冻结 bash oracle）、d-套件（确定性/健壮性/模糊奇偶/并发） | 否 | push 到 main / PR（CI 三平台 × 两 Python 矩阵） |
| **L2 结构 + 全会话回放** | `test_structure.py`（跨文件不变量）+ `test_e2e_session.py`（S1–S7：按真实会话顺序回放 hook 序列，断言 trace/plan/快照的状态演化） | 否 | push 到 main / PR |
| **L3 live 场景套件** | `scripts/dev-e2e.sh`：真实无头 Claude（`--plugin-dir` 加载本插件）跑 SC-1~SC-6，每条核心纪律一个实弹场景 | **是** | 本地按需；CI：push main + 每日 + 手动 |
| **L4 符合性审计** | 3 个独立 AI 评委按 [`tests/e2e_workflow_rubric.md`](../tests/e2e_workflow_rubric.md) 逐行多数票打分，验证是否符合官方 harness engineering 原则 | **是** | 跟随 L3 full |

## 前置条件

| 层 | 需要 |
| --- | --- |
| L1 + L2 | Python 3.9+、pytest（`python3 -m pip install pytest`）、git。可选装 `jsonschema`（多跑 1 项 schema 全量校验，缺席时自动 skip） |
| manifest 校验 | Claude Code CLI（`claude` 在 PATH 上）；**不调模型、无需登录** |
| L3 + L4 | `claude` CLI + 鉴权：本地用你已登录的 Claude Code（订阅）即可；CI 用 `ANTHROPIC_API_KEY` |

所有命令在**仓库根目录**执行（pytest 依赖 `tests` 包的相对导入）。

## 平台支持

| 内容 | macOS / Linux | Windows |
| --- | --- | --- |
| L1 smoke + d1/d3/d9 | ✅ | ✅（CI 矩阵含 `windows-latest`，走 Git Bash） |
| L1 parity 系列（parity / parity_extra / d7） | ✅（需 git 历史中的旧 bash 实现，浅克隆时自动 skip） | ⛔ **自动跳过**——oracle 需要 Unix 工具链，`skipif` 干净跳过不报错 |
| L2 structure + 全会话回放 | ✅ | ✅（已在 CI 的 Windows job 步骤中） |
| manifest 校验 | ✅ | ✅ |
| L3/L4 live（dev-e2e.sh） | ✅（实测验证过） | ⚠️ 理论可行：在 **Git Bash** 中运行（与插件本身的 Windows 支持方式一致），解释器按 `python3 → python → py -3` 自动探测（可用 `HARNESS_PY` 覆盖）；**尚未在 Windows 上实弹验证** |

CI 分工：Windows job 跑 smoke + structure + 回放；ubuntu job 跑全量确定性套件（含 d-套件）和 live e2e；macOS job 补 parity。本地 Windows 上手动 `python -m pytest tests` 可以全跑（parity 自动跳过）。

## 怎么跑

### L1 + L2 — 确定性套件（~1 分钟，不调模型）

```bash
python3 -m pytest tests -v
```

预期收尾：`348 passed, 1 skipped, 2 deselected`——skipped 是可选的 jsonschema 校验，
deselected 是 live 层（默认永不触发）。失败即代码或结构被改坏，看对应断言即可。

只跑新增层：`python3 -m pytest tests/test_structure.py tests/test_e2e_session.py -v`

### Manifest 严格校验（秒级，不调模型）

```bash
claude plugin validate . --strict
```

预期：`✔ Validation passed`。

### L3 — live 场景套件（真实 Claude）

```bash
bash scripts/dev-e2e.sh probe   # 最小实弹（~1-2 分钟，一次极小会话）
bash scripts/dev-e2e.sh full    # 全 6 场景 + 3 评委审计（~15-25 分钟）
```

- **先跑 probe 试水**：验证「headless 下插件 hooks 真触发」这一根本假设，同时探明配额窗口是否可用。
- `full` 按 probe → SC-1…SC-6 → 审计顺序执行；probe 硬失败会直接中止（插件没在 headless 下工作，后面没有意义）。
- 实测一轮 full 的用量按 API 计价口径约 $3（订阅登录走额度，无账单）。
- 产物目录默认 `mktemp`，**输出最后的 `artifacts:` 行会打印路径**；要固定位置用 `E2E_OUT_DIR=/path bash scripts/dev-e2e.sh full`。

单场景调试与重审：

```bash
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh scenario SC-3   # 单场景
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh scenario SC-5   # 依赖同目录已有 SC-2 产物，否则报错退出 2
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh audit-only      # 复用已有证据，只重跑 3 评委
```

环境变量：`E2E_MODEL`（换模型，默认你的 Claude Code 默认模型）、`E2E_MAX_BUDGET`（失控保险，默认不设）、
`E2E_ISOLATE_HOME=1`（scratch HOME 全隔离，需 `ANTHROPIC_API_KEY`，CI 用）。

也可经 pytest 触发（三重门禁，`pytest tests` 默认永不触发）：

```bash
HARNESS_LIVE_E2E=1 python3 -m pytest tests/test_live_e2e.py -v -s
```

### 读懂输出

```
  [ok]   SC-3:gate_remediation_done      ← 硬断言（文件系统副作用）：失败 = harness 问题
  [ok] ~ SC-3:stop_hook_exit_2_seen      ← 软断言（带 ~）：失败只 warn，不挂套件
```

**退出码**：`0` 全部硬断言通过；`1` 有硬断言失败；`2` 用法/环境错误；`3` **不确定**——上游限流
（429 / 订阅 5 小时配额窗口耗尽）中断了会话，证据保留但不判定，后续场景自动跳过以免空烧配额，
等窗口恢复后重跑即可。注意 `… | tee log` 会被管道吃掉退出码，要取真实结果用 `set -o pipefail`。

### 产物布局（$OUT）

```
probe.jsonl(.err/.rc)      原始 stream-json + stderr + claude 退出码
evidence-probe.json        probe 的硬/软断言结果
sc-1/ … sc-6/
  proj/                    场景的临时项目（.harness/state/trace.jsonl 是硬断言的依据）
  run.jsonl(.err/.rc)      该场景的原始会话流
  evidence-SC-N.json       该场景的断言结果
evidence.json              合并证据（+ pytest 摘要 + 成本合计）—— 审计的唯一输入
audit-prompt.txt           喂给评委的完整 prompt（rubric + 证据）
judge-{1,2,3}.json         三个评委的原始输出
audit.json                 多数票合成（rows / failing / disputed）
```

调试某个失败场景：先看 `evidence-SC-N.json` 哪条硬断言挂了，再对照 `sc-N/proj/.harness/state/trace.jsonl`
与 `sc-N/run.jsonl`（hook_started / hook_response 事件含每个 hook 的输出与退出码）。

### 排障速查

| 现象 | 处理 |
| --- | --- |
| `claude CLI not found` | 安装 Claude Code，或检查 PATH |
| 退出码 3 / `[INCONCLUSIVE]` | 订阅配额窗口耗尽，等恢复后重跑（先 `probe` 试水） |
| `E2E_ISOLATE_HOME=1 … requires ANTHROPIC_API_KEY` | 隔离模式抹掉登录态，必须配 API key；本地直接去掉该变量用登录态 |
| SC-5/SC-6 报 `needs a prior SC-2 run` | 单场景模式下先在同一 `E2E_OUT_DIR` 跑 `scenario SC-2`（或直接 `full`） |
| 评委输出解析失败（warn） | 单评委失败按余下评委多数票继续；全失败时审计跳过不挂套件，可 `audit-only` 重试 |

## CI 配置

工作流已就位，推到 GitHub 后：

- **`.github/workflows/test.yml`**（L1+L2）：push main / PR 自动跑，三平台 × Python 3.9/3.12，无需任何配置。
- **`.github/workflows/e2e.yml`**：`plugin-validate` job 始终跑（免费无 key）；`live-e2e` job 在 push main、
  每日 03:00 UTC cron、手动 dispatch 时跑，需在仓库 **Settings → Secrets and variables → Actions** 配
  `ANTHROPIC_API_KEY`——secret 缺失时干净跳过不报红。限流中断在 CI 中记为 warning 而非失败。
  运行产物（evidence / audit / 各场景 run.jsonl）作为 artifact 上传，可在 Actions 页面下载复查。

## L3 场景 ↔ 纪律映射

| 场景 | 验证的纪律 | 硬断言（文件系统副作用） |
| --- | --- | --- |
| probe | 插件在 headless 下加载、hooks 触发 | trace.jsonl 出现 `session_start`；system/init 列出插件且无错误 |
| SC-1 | `/harness-kit:init` 真实斜杠命令路径 | config / CLAUDE.md / pre-commit 落盘 |
| SC-2 | 计划门禁 + Definition of Done 闭环 | `auto-*.md` 计划落盘；hello.py 存在；trace 含 session_start/end |
| SC-3 | strict Stop 门：拦截 → 按 stderr 指引修复 → 通过 | `FIXED` 被创建；trace `session_end` 先 failed 后 passed |
| SC-4 | 循环检测实弹（同文件 5 次编辑） | `loop-*.json` 计数 ≥ 阈值 |
| SC-5 | 生成/评估分离（evaluator 子代理） | 运行完成；VERDICT / evaluator trace 事件（软） |
| SC-6 | 跨会话连续性（SessionStart handoff） | 新增 `session_start` 入 trace（按基线计数）；回答引用上次 plan（软） |

**断言分级**：硬断言优先读文件系统副作用（trace.jsonl、plan 文件、loop 计数器）——不依赖模型配合；仅有的两类 stream 硬断言（插件加载、运行完成）来自稳定的 `system/init` 与 `result` 事件。依赖较新 `--include-hook-events` flag 的 hook 生命周期事件一律软断言（warn 不 fail）。

## 成本与隔离

- 设计前提是**验证质量优先于 token 成本**：默认用你的默认（强）模型，不设预算上限。`E2E_MODEL` 可换模型，`E2E_MAX_BUDGET` 是失控保险逃生口（默认不设）。
- 本地默认复用你已登录的 Claude Code（订阅鉴权），不隔离 `$HOME`。
- CI 里设 `E2E_ISOLATE_HOME=1` + `ANTHROPIC_API_KEY` secret：scratch HOME，完全隔离全局配置。secret 缺失时 live job 干净跳过。

## L4 审计如何工作

`dev-e2e.sh full` 把每个场景的硬/软断言结果合并为 `evidence.json`（附带确定性套件的 pytest 摘要），
然后并行派 3 个独立 Claude 评委：只依据 evidence 按 rubric 逐行打 `pass / partial / fail / n-a`，
按**评委数**多数票合成最终结论（分歧行标 `disputed`），任何可判定行多数 `fail` 即整条流水线失败。
