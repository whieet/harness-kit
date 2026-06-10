# Harness Kit 配置指南 — `.harness/config.json`

[English](./configuration.en.md) · **简体中文**

> **这份文档主要写给 AI（Claude Code）看。**
> 用 Harness Kit 时你通常**不手写**配置——而是用自然语言告诉 Claude Code 你想要什么（「加一个 `npm test` 验证门」「关掉循环检测」「禁止 UI 层直连数据库」），Claude Code 照本指南编辑 `.harness/config.json`。
> 下面给出每个字段的**类型 / 默认 / 作用 / 示例**，以及「用户说 → 怎么改」的常见配方，让 AI 配得准、配得稳。

---

## 给 AI 的操作约定

- **文件位置**：项目根的 `.harness/config.json`（随项目入库；由 `/harness-kit:init` 首次生成）。
- **生效方式**：保存即生效，无需重启；下次 hook / 命令触发时读取。
- **必须是合法 JSON**：标准 JSON **不允许注释，也不允许尾逗号**。本指南示例里的 `//` 注释仅作讲解，写入文件前务必删掉。
- **最小改动原则**：只改用户要求的字段，其它保持原样。**缺省字段一律走默认值**——不要为了「显式」把一堆默认值灌进配置。
- **拿不准就查**：字段语义以本指南 + [`../templates/config.schema.json`](../templates/config.schema.json)（机器可读 schema）为准；不要臆造字段名或取值。
- **改完自检**：跑 `/harness-kit:verify` 确认 JSON 合法、门能跑通。
- **已废弃**：`phases` 字段已废弃，别再写；能力开关一律用 `enabledCapabilities`。

---

## 最小可用配置

只需声明项目类型 + 哪些文件改动需要计划，其余全走默认：

```json
{
  "projectType": "custom",
  "plan": { "codeGlob": "\\.(ts|tsx|py)$" }
}
```

---

## 完整示例（带讲解注释）

> ⚠️ 下面的 `//` 注释**仅用于讲解**。真实 `.harness/config.json` 是标准 JSON，**不能带注释**——写入前请删掉所有 `//`。

```jsonc
{
  "projectType": "web",                  // godot | web | custom，仅影响 init 脚手架与 advisor 文案
  "verificationMode": "strict",          // strict=不过则拦截收工；advisory=只告警。默认 strict

  "verifyCmd": "harness-verify",         // 验证入口（Stop hook / pre-commit / /verify 共用），默认即此
  "buildCmd": "npm run build",           // 构建命令，advisor 会展示
  "testCmd": "npm test -- --run",        // 测试命令

  "gates": [                             // 有序验证门；harness-verify 逐个跑
    { "name": "eslint",    "command": "npx --no-install eslint .",     "blocking": true,  "tier": "fast" },
    { "name": "typecheck", "command": "npx --no-install tsc --noEmit", "blocking": true,  "tier": "full" },
    { "name": "layering",  "command": "harness-check-layering",        "blocking": true,  "tier": "fast" },
    { "name": "doc-links", "command": "harness-doc-links",             "blocking": true,  "tier": "fast" },
    { "name": "tests",     "command": "npm test -- --run",             "blocking": true,  "tier": "full" },
    { "name": "plan-dod",  "command": "harness-check-plan-dod",        "blocking": true,  "tier": "fast" },
    { "name": "doc-gardening", "command": "harness-doc-gardening",     "blocking": false, "tier": "fast" }
  ],

  "layeringRules": [                     // 依赖方向约束；harness-check-layering 检查
    { "scope": "src/ui/**/*.{ts,tsx}",     "forbidden": "from\\s+['\"][^'\"]*(db|prisma)", "message": "UI 不得直连数据库，走 API/service" },
    { "scope": "src/domain/**/*.{ts,tsx}", "forbidden": "from\\s+['\"]react",              "message": "domain 逻辑不得引入 React" }
  ],

  "plan": {
    "dir": "docs/exec-plans",            // 计划根，下设 active/ 与 completed/。默认 docs/exec-plans
    "codeGlob": "\\.(ts|tsx)$",          // 哪些文件改动需先有计划（正则）。空字符串=关闭计划门
    "statusField": "status",             // 计划头里表示状态的字段名。默认 status
    "completedValue": "completed",       // 表示「已完成」的状态值。默认 completed
    "checklistRegex": "^- \\[ \\]",      // 匹配未勾选 DoD 项的正则。默认即此
    "requiredFields": ["status", "created", "Definition of Done"]  // 完成的计划必须含的字段
  },

  "docs": {
    "keyDocs": [                         // 会话开始时注入「交接」的关键文档
      { "path": "ARCHITECTURE.md", "note": "模块边界" }
    ],
    "scanRoots": ["docs"],               // 递归扫死链的目录（顶层 *.md 总会扫）。默认 ["docs"]
    "architecturePath": "ARCHITECTURE.md",  // 被 doc-gardening 审计「漂移」的架构文档
    "qualityPath": "docs/QUALITY.md",       // 被审计「过期」的质量文档
    "stalenessDays": 14,                    // 过期阈值（天）。默认 14
    "layerBaseDir": "src",                  // 其直接子目录视为架构「层」（反向漂移检测）
    "layerIgnoreDirs": ["assets", "types"], // 反向漂移检测豁免的子目录
    "namingGlob": "src/components/**/*.{ts,tsx}",  // 命名规范检查的文件
    "namingDisallow": "[ ]"                 // 文件名（去扩展名）禁止匹配的正则
  },

  "metrics": [                           // advisor 仪表盘：按 glob 数文件
    { "name": "completed",  "glob": "docs/exec-plans/completed/*.md", "exclude": "gitkeep" },
    { "name": "components", "glob": "src/components/**/*.{ts,tsx}" }
  ],

  "enabledCapabilities": {               // 各 harness 行为的开关（缺省=稳定项开、实验项关）
    "planGate": true,                    // 编辑无计划代码时自动补计划骨架
    "loopDetection": true,               // 单文件反复改时预警
    "toolTrace": true,                   // 记录工具调用，供 trace 分析
    "evaluator": true,                   // Stop 门在代码有改动时「推荐」跑评估
    "contextSnapshot": true,             // 压缩前快照、压缩后再注入
    "evaluatorAutoDispatch": false       // 实验：Stop 时自动派评估子代理。默认关
  },

  "effortRouting": { "enabled": false }, // 开则低/中强度回合只跑 fast 档门。默认关

  "loopDetection": {
    "threshold": 5,                      // 同一文件改满几次预警。默认 5
    "ignoreGlobs": ["*.lock", "dist/*"]  // 不计入循环计数的文件
  },

  "evaluator": {
    "enabled": false,                    // 是否在 Stop 末段真正跑「怀疑式」评估。默认关
    "rubricPath": ".harness/rubric.md",  // 评分标准文档
    "mode": "advisory"                   // advisory=只报分；strict=分数不达标则拦截。默认 advisory
  },

  "verificationRecipe": {                // 把 rubric 维度映射到验证命令/MCP 工具（evaluator 用）
    "functionality": "npx playwright test",
    "quality": "harness-verify"
  }
}
```

---

## 字段速查

### 顶层
| 字段 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `projectType` | `"godot"｜"web"｜"custom"` | — | 预设身份，仅影响 init 脚手架与 advisor 文案，脚本逻辑不依赖它 |
| `verificationMode` | `"advisory"｜"strict"` | `strict` | Stop 验证门严格度：strict 不过则拦截收工；advisory 只告警 |
| `verifyCmd` | string | `harness-verify` | 验证入口，Stop hook / git pre-commit / `/harness-kit:verify` 共用 |
| `buildCmd` | string | — | 构建 / 编译命令，advisor 与检查清单会展示 |
| `testCmd` | string | — | 测试命令 |

### `gates[]` — 验证门（按数组顺序执行）
| 子字段 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `name` | string | **必填** | 门的可读名 |
| `command` | string | **必填** | 要跑的 shell 命令。内置门 `harness-check-layering` / `harness-doc-links` / `harness-doc-gardening` / `harness-check-plan-dod` 由插件 bin 提供 |
| `blocking` | bool | `true` | `false`=软门：失败只告警、不致整体失败 |
| `tier` | `"fast"｜"full"` | `full` | 努力分级档；仅当 `effortRouting.enabled` 时，低/中强度回合只跑 `fast` 门。路由关闭时此字段被忽略、所有门都跑 |
| `skipWhenProcess` | string | — | 命中同名进程在跑时跳过该门（如 `Godot` 避开编辑器项目锁）|

### `layeringRules[]` — 依赖方向约束
| 子字段 | 类型 | 作用 |
| --- | --- | --- |
| `scope` | glob | 要检查的文件，如 `src/ui/**/*.{ts,tsx}` |
| `forbidden` | regex | scope 内文件中**不得出现**的内容（一条非法依赖）|
| `message` | string | 违反时显示的修复提示 |

### `plan` — 计划生命周期
| 子字段 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `dir` | string | `docs/exec-plans` | 计划根目录，下设 `active/`、`completed/` |
| `codeGlob` | regex | — | 哪些文件路径的改动需要先有覆盖计划。**空字符串 = 关闭计划门** |
| `template` | string | 内置 `plan-template.md` | 计划脚手架模板路径 |
| `statusField` | string | `status` | 从计划头解析状态用的字段名 |
| `completedValue` | string | `completed` | 表示「已完成」、应移入 `completed/` 的状态值 |
| `checklistRegex` | regex | `^- \[ \]` | 匹配一条未勾选 DoD 项 |
| `requiredFields` | string[] | — | 每个完成的计划必须包含的字段（模板合规检查）|

### `docs` — 文档相关路径
| 子字段 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `keyDocs` | `{path, note}[]` | — | 会话开始时注入交接的关键文档 |
| `scanRoots` | string[] | `["docs"]` | 递归扫死链的目录（顶层 `*.md` 总会扫）|
| `architecturePath` | string | — | 被审计「漂移」的架构文档 |
| `qualityPath` | string | — | 被审计「过期」的质量/评分文档 |
| `stalenessDays` | int | `14` | `qualityPath` 过期阈值（天）|
| `placeholderPatterns` | string[] | 内置中英常见词 | 标记「未完成占位文档」的子串 |
| `layerPathRegex` | regex | — | 从架构文档提取被引用的层路径；**前向漂移**：引用了但磁盘已无 |
| `layerBaseDir` | string | — | 其直接子目录即架构「层」；**反向漂移**：磁盘有但架构文档没声明 |
| `layerIgnoreDirs` | string[] | — | 反向漂移检测豁免的子目录（如 `utils`、`_autoload`）|
| `namingGlob` | glob | — | 命名规范检查的文件 |
| `namingDisallow` | regex | — | 文件名（去扩展名）**不得匹配**的正则，如 `[A-Z]` 强制 snake_case |

### `metrics[]` — advisor 仪表盘计数
| 子字段 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `name` | string | **必填** | 指标名 |
| `glob` | glob | **必填** | 其匹配文件数即该指标值 |
| `exclude` | regex | — | 命中的文件从计数中排除（如排除 `_template.md`）|

### `enabledCapabilities` — 行为开关（缺省：稳定项开、实验项关）
| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `planGate` | `true` | 编辑无计划代码时自动补计划骨架 |
| `loopDetection` | `true` | 单文件编辑循环预警 |
| `toolTrace` | `true` | 记录工具调用/失败，供 trace 分析 |
| `evaluator` | `true` | 代码有改动时，Stop 门**推荐**跑评估（推荐≠自动执行）|
| `contextSnapshot` | `true` | 压缩前快照状态、压缩后再注入 |
| `evaluatorAutoDispatch` | `false` | 实验：Stop 时自动派评估子代理（非阻塞，仅注入上下文），另需接 `hooks/optional-auto-eval.json` |

### `effortRouting`
| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `enabled` | `false` | 关=不论强度都跑全部门（安全默认）；开=按 `$CLAUDE_EFFORT` 路由，低/中强度只跑 `fast` 门 |

### `loopDetection`
| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `threshold` | `5` | 同一文件在一次会话改满几次即预警 |
| `ignoreGlobs` | — | 不计入循环计数的文件（生成物、锁文件等）|

### `evaluator` — 生成/评估分离
| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `enabled` | `false` | 当 `plan.codeGlob` 命中的代码有改动时，是否在 Stop 末段**真正跑**怀疑式评估 |
| `rubricPath` | — | 每项目评分标准文档，如 `.harness/rubric.md` |
| `mode` | `advisory` | `strict`=分数不达标则拦截收工；`advisory`=只报分 |

> **两个 evaluator 开关别混淆**：`enabledCapabilities.evaluator` 控制 Stop 门是否**推荐**你跑评估；`evaluator.enabled` 控制 Stop 门是否**自动执行**评估这一段。想「收工时一定要独立打分」，把 `evaluator.enabled` 设 `true`。

### `verificationRecipe`
键是 rubric 维度名（如 `functionality` / `visual` / `integration` / `quality`），值是验证该维度的命令或 MCP 工具名字符串。把 MCP 工具名（如 `play_scene`）从插件代码里挪到项目配置里，供 evaluator 子代理参考。

```json
"verificationRecipe": {
  "functionality": "npx playwright test (或项目 e2e)",
  "quality": "harness-verify (eslint + tsc + layering)"
}
```

---

## 常见配方（用户说 → 你怎么改）

| 用户想要 | 怎么改 |
| --- | --- |
| 「加一个跑测试的门」 | 往 `gates[]` 末尾加 `{ "name": "tests", "command": "<测试命令>", "blocking": true, "tier": "full" }` |
| 「这个门只告警、别拦我」 | 把该门 `blocking` 设为 `false` |
| 「禁止 X 层引用 Y」 | 往 `layeringRules[]` 加 `{ scope, forbidden(正则), message }` |
| 「不想每次都要先写计划」 | `enabledCapabilities.planGate = false`，或把 `plan.codeGlob` 设为 `""` |
| 「同一文件要改很多次才提醒」 | 调高 `loopDetection.threshold`；生成文件加进 `ignoreGlobs` |
| 「收工前帮我独立打分」 | `evaluator.enabled = true`（要硬拦再设 `mode: "strict"`），确保 `rubricPath` 指向 rubric |
| 「小改动别跑全套门」 | `effortRouting.enabled = true`，重门标 `"tier": "full"`、轻门标 `"fast"` |
| 「换计划存放目录」 | 改 `plan.dir` |
| 「让评估用某工具验证某维度」 | 在 `verificationRecipe` 加 `"<维度>": "<命令或 MCP 工具>"` |
| 「彻底放松，只告警不拦截」 | `verificationMode = "advisory"` |

---

## 校验改动

改完 `.harness/config.json` 后，在 Claude Code 里跑：

```text
/harness-kit:verify
```

跑通即配置生效；JSON 不合法或某个门报错会直接显示出来。

完整机器可读 schema（draft-07）：[`../templates/config.schema.json`](../templates/config.schema.json)。
