# Harness Kit Configuration Guide — `.harness/config.json`

**English** · [简体中文](./configuration.md)

> **This document is written mainly for the AI (Claude Code).**
> When you use Harness Kit you usually **don't hand-write** config — you tell Claude Code what you want in plain language ("add an `npm test` gate", "turn off loop detection", "forbid the UI layer from importing the DB"), and Claude Code edits `.harness/config.json` per this guide.
> Below is every field's **type / default / purpose / example**, plus "user says → how to change it" recipes, so the AI configures accurately and safely.

---

## Conventions for the AI

- **Location**: `.harness/config.json` at the project root (committed with the project; first created by `/harness-kit:init`).
- **Takes effect**: on save, no restart needed; read on the next hook / command.
- **Must be valid JSON**: standard JSON allows **no comments and no trailing commas**. The `//` comments in this guide are explanatory only — strip them before writing the file.
- **Minimal-change principle**: only touch the fields the user asked about; leave the rest as-is. **Omitted fields fall back to defaults** — don't pour a wall of default values into the config just to be "explicit".
- **When unsure, look it up**: field semantics are governed by this guide + [`../templates/config.schema.json`](../templates/config.schema.json) (machine-readable schema); don't invent field names or values.
- **Self-check after editing**: run `/harness-kit:verify` to confirm the JSON is valid and the gates run.
- **Deprecated**: the `phases` field is deprecated — don't write it; use `enabledCapabilities` for behavior toggles.

---

## Minimal working config

Just declare the project type + which file edits require a plan; everything else uses defaults:

```json
{
  "projectType": "custom",
  "plan": { "codeGlob": "\\.(ts|tsx|py)$" }
}
```

---

## Full example (annotated)

> ⚠️ The `//` comments below are **explanatory only**. A real `.harness/config.json` is standard JSON and **cannot contain comments** — strip every `//` before writing.

```jsonc
{
  "projectType": "web",                  // godot | web | custom; only affects the init scaffolder & advisor copy
  "verificationMode": "strict",          // strict = a failure blocks completion; advisory = warn only. Default strict

  "verifyCmd": "harness-verify",         // verify entrypoint (shared by the Stop hook / pre-commit / /verify). Default as shown
  "buildCmd": "npm run build",           // build command, surfaced by the advisor
  "testCmd": "npm test -- --run",        // test command

  "gates": [                             // ordered verification gates; harness-verify runs them in turn
    { "name": "eslint",    "command": "npx --no-install eslint .",     "blocking": true,  "tier": "fast" },
    { "name": "typecheck", "command": "npx --no-install tsc --noEmit", "blocking": true,  "tier": "full" },
    { "name": "layering",  "command": "harness-check-layering",        "blocking": true,  "tier": "fast" },
    { "name": "doc-links", "command": "harness-doc-links",             "blocking": true,  "tier": "fast" },
    { "name": "tests",     "command": "npm test -- --run",             "blocking": true,  "tier": "full" },
    { "name": "plan-dod",  "command": "harness-check-plan-dod",        "blocking": true,  "tier": "fast" },
    { "name": "doc-gardening", "command": "harness-doc-gardening",     "blocking": false, "tier": "fast" }
  ],

  "layeringRules": [                     // dependency-direction constraints; checked by harness-check-layering
    { "scope": "src/ui/**/*.{ts,tsx}",     "forbidden": "from\\s+['\"][^'\"]*(db|prisma)", "message": "UI must not hit the DB directly; go via an API/service" },
    { "scope": "src/domain/**/*.{ts,tsx}", "forbidden": "from\\s+['\"]react",              "message": "domain logic must not import React" }
  ],

  "plan": {
    "dir": "docs/plans",            // plan root, with active/ and completed/ under it. Default docs/plans
    "codeGlob": "\\.(ts|tsx)$",          // which file edits require a covering plan (regex). Empty string = plan gate off
    "statusField": "status",             // field name parsed from a plan header for its status. Default status
    "completedValue": "completed",       // status value meaning "done". Default completed
    "checklistRegex": "^- \\[ \\]",      // regex matching an unchecked DoD item. Default as shown
    "requiredFields": ["status", "created", "Definition of Done"]  // fields every completed plan must contain
  },

  "docs": {
    "keyDocs": [                         // docs injected into the session "handoff"
      { "path": "ARCHITECTURE.md", "note": "module boundaries" }
    ],
    "scanRoots": ["docs"],               // dirs scanned recursively for dead links (top-level *.md always scanned). Default ["docs"]
    "architecturePath": "ARCHITECTURE.md",  // architecture doc audited for "drift" by doc-gardening
    "qualityPath": "docs/QUALITY.md",       // quality doc audited for "staleness"
    "stalenessDays": 14,                    // staleness threshold (days). Default 14
    "layerBaseDir": "src",                  // its immediate subdirs are the architecture "layers" (reverse-drift check)
    "layerIgnoreDirs": ["assets", "types"], // subdirs exempt from the reverse-drift check
    "namingGlob": "src/components/**/*.{ts,tsx}",  // files whose names are checked
    "namingDisallow": "[ ]"                 // regex the basename (no ext) must NOT match
  },

  "metrics": [                           // advisor dashboard: count files by glob
    { "name": "completed",  "glob": "docs/plans/completed/*.md", "exclude": "gitkeep" },
    { "name": "components", "glob": "src/components/**/*.{ts,tsx}" }
  ],

  "enabledCapabilities": {               // per-behavior switches (defaults: stable on, experimental off)
    "planGate": true,                    // auto-scaffold a plan when editing un-planned code
    "loopDetection": true,               // warn on repeated edits to one file
    "toolTrace": true,                   // record tool calls for trace analysis
    "evaluator": true,                   // Stop gate "recommends" the evaluator when code changed
    "contextSnapshot": true,             // snapshot before compaction, re-inject after
    "evaluatorAutoDispatch": false       // EXPERIMENTAL: auto-dispatch the evaluator at Stop. Default off
  },

  "effortRouting": { "enabled": false }, // on => low/medium-effort turns run only fast-tier gates. Default off

  "loopDetection": {
    "threshold": 5,                      // warn after this many edits to one file. Default 5
    "ignoreGlobs": ["*.lock", "dist/*"]  // files excluded from loop counting
  },

  "evaluator": {
    "enabled": false,                    // whether the Stop gate actually RUNS the skeptical evaluator. Default off
    "rubricPath": ".harness/rubric.md",  // scoring rubric doc
    "mode": "advisory"                   // advisory = score only; strict = a sub-threshold score blocks. Default advisory
  },

  "verificationRecipe": {                // map each rubric dimension to a verify command / MCP tool (used by the evaluator)
    "functionality": "npx playwright test",
    "quality": "harness-verify"
  }
}
```

---

## Field reference

### Top level
| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `projectType` | `"godot"｜"web"｜"custom"` | — | Preset identity; only affects the init scaffolder & advisor copy — scripts never branch on it |
| `verificationMode` | `"advisory"｜"strict"` | `strict` | Stop-gate strictness: strict blocks completion on failure; advisory warns only |
| `verifyCmd` | string | `harness-verify` | Verify entrypoint, shared by the Stop hook / git pre-commit / `/harness-kit:verify` |
| `buildCmd` | string | — | Build/compile command, surfaced by the advisor & checklist |
| `testCmd` | string | — | Test command |

### `gates[]` — verification gates (run in array order)
| Subfield | Type | Default | Purpose |
| --- | --- | --- | --- |
| `name` | string | **required** | Human-readable gate label |
| `command` | string | **required** | Shell command to run. Bundled gates `harness-check-layering` / `harness-doc-links` / `harness-doc-gardening` / `harness-check-plan-dod` come from the plugin bin |
| `blocking` | bool | `true` | `false` = soft gate: a failure warns but doesn't fail the aggregate |
| `tier` | `"fast"｜"full"` | `full` | Effort-routing tier; only when `effortRouting.enabled`, low/medium turns run just `fast` gates. Ignored (all gates run) when routing is off |
| `skipWhenProcess` | string | — | Skip this gate if a process of this name is running (e.g. `Godot` to avoid the editor project lock) |

### `layeringRules[]` — dependency-direction constraints
| Subfield | Type | Purpose |
| --- | --- | --- |
| `scope` | glob | Files to check, e.g. `src/ui/**/*.{ts,tsx}` |
| `forbidden` | regex | Content that must **not** appear in files under scope (one illegal dependency) |
| `message` | string | Remediation text shown on violation |

### `plan` — plan lifecycle
| Subfield | Type | Default | Purpose |
| --- | --- | --- | --- |
| `dir` | string | `docs/plans` | Plan root; `active/` and `completed/` live under it |
| `codeGlob` | regex | — | Which file paths require a covering plan. **Empty string = plan gate off** |
| `template` | string | bundled `plan-template.md` | Plan scaffold template path |
| `statusField` | string | `status` | Field name parsed for a plan's status |
| `completedValue` | string | `completed` | Status value meaning "done" → must live in `completed/` |
| `checklistRegex` | regex | `^- \[ \]` | Matches one unchecked DoD item |
| `requiredFields` | string[] | — | Fields every completed plan must contain (template-compliance check) |

### `docs` — doc-related paths
| Subfield | Type | Default | Purpose |
| --- | --- | --- | --- |
| `keyDocs` | `{path, note}[]` | — | Docs surfaced in the session handoff |
| `scanRoots` | string[] | `["docs"]` | Dirs scanned recursively for dead links (top-level `*.md` always scanned) |
| `architecturePath` | string | — | Architecture doc audited for "drift" |
| `qualityPath` | string | — | Quality/score doc audited for "staleness" |
| `stalenessDays` | int | `14` | `qualityPath` staleness threshold (days) |
| `placeholderPatterns` | string[] | built-in EN+CN words | Substrings marking unfinished placeholder docs |
| `layerPathRegex` | regex | — | Extracts referenced layer paths from the architecture doc; **forward drift**: referenced but gone from disk |
| `layerBaseDir` | string | — | Its immediate subdirs are the architecture layers; **reverse drift**: on disk but not declared |
| `layerIgnoreDirs` | string[] | — | Subdirs exempt from the reverse-drift check (e.g. `utils`, `_autoload`) |
| `namingGlob` | glob | — | Files whose names are checked |
| `namingDisallow` | regex | — | Regex the basename (no ext) must **not** match, e.g. `[A-Z]` to enforce snake_case |

### `metrics[]` — advisor dashboard counts
| Subfield | Type | Default | Purpose |
| --- | --- | --- | --- |
| `name` | string | **required** | Metric name |
| `glob` | glob | **required** | Its match count is the metric value |
| `exclude` | regex | — | Matching files excluded from the count (e.g. `_template.md`) |

### `enabledCapabilities` — behavior switches (defaults: stable on, experimental off)
| Field | Default | Purpose |
| --- | --- | --- |
| `planGate` | `true` | Auto-scaffold a plan when editing un-planned code |
| `loopDetection` | `true` | Per-file edit-loop nudge |
| `toolTrace` | `true` | Record tool calls/failures for trace analysis |
| `evaluator` | `true` | Stop gate **recommends** the evaluator when code changed (recommend ≠ auto-run) |
| `contextSnapshot` | `true` | Snapshot state before compaction, re-inject after |
| `evaluatorAutoDispatch` | `false` | EXPERIMENTAL: auto-dispatch the evaluator subagent at Stop (non-blocking, context-only); also requires wiring `hooks/optional-auto-eval.json` |

### `effortRouting`
| Field | Default | Purpose |
| --- | --- | --- |
| `enabled` | `false` | Off = always run all gates (safe default); On = route by `$CLAUDE_EFFORT`, low/medium runs only `fast` gates |

### `loopDetection`
| Field | Default | Purpose |
| --- | --- | --- |
| `threshold` | `5` | Warn after this many edits to one file in a session |
| `ignoreGlobs` | — | Files excluded from loop counting (generated files, lockfiles, …) |

### `evaluator` — Generator/Evaluator separation
| Field | Default | Purpose |
| --- | --- | --- |
| `enabled` | `false` | Whether the Stop gate actually **runs** the skeptical evaluator when code matching `plan.codeGlob` changed |
| `rubricPath` | — | Per-project rubric doc, e.g. `.harness/rubric.md` |
| `mode` | `advisory` | `strict` = a sub-threshold score blocks completion; `advisory` = score only |

> **Don't confuse the two evaluator switches**: `enabledCapabilities.evaluator` controls whether the Stop gate **recommends** running the evaluator; `evaluator.enabled` controls whether the Stop gate **runs** it. For "always score independently before finishing", set `evaluator.enabled = true`.

### `verificationRecipe`
Keys are rubric dimension names (e.g. `functionality` / `visual` / `integration` / `quality`); values are the command or MCP tool string that verifies that dimension. Keeps MCP tool names (e.g. `play_scene`) out of plugin code and in project config, for the evaluator subagent to reference.

```json
"verificationRecipe": {
  "functionality": "npx playwright test (or the project e2e)",
  "quality": "harness-verify (eslint + tsc + layering)"
}
```

---

## Recipes (user says → how you change it)

| User wants | How to change it |
| --- | --- |
| "Add a gate that runs tests" | Append to `gates[]`: `{ "name": "tests", "command": "<test cmd>", "blocking": true, "tier": "full" }` |
| "This gate should only warn, not block me" | Set that gate's `blocking` to `false` |
| "Forbid layer X from importing Y" | Add to `layeringRules[]`: `{ scope, forbidden(regex), message }` |
| "Stop forcing a plan every time" | `enabledCapabilities.planGate = false`, or set `plan.codeGlob` to `""` |
| "Warn only after many edits to one file" | Raise `loopDetection.threshold`; add generated files to `ignoreGlobs` |
| "Score my work independently before finishing" | `evaluator.enabled = true` (add `mode: "strict"` to hard-block), ensure `rubricPath` points at the rubric |
| "Don't run the full gate set on tiny changes" | `effortRouting.enabled = true`; tag heavy gates `"tier": "full"`, light ones `"fast"` |
| "Move where plans are stored" | Change `plan.dir` |
| "Make the evaluator verify a dimension with some tool" | Add `"<dimension>": "<command or MCP tool>"` to `verificationRecipe` |
| "Loosen everything to warn-only" | `verificationMode = "advisory"` |

---

## Verifying your changes

After editing `.harness/config.json`, in Claude Code run:

```text
/harness-kit:verify
```

If it passes, the config is live; invalid JSON or a failing gate is reported right away.

Full machine-readable schema (draft-07): [`../templates/config.schema.json`](../templates/config.schema.json).
