# Harness Kit

**English** | [中文](README.md) · MIT License

> Turn any repo into a self-verifying **Plan → Build → Verify → Done** loop — a project-agnostic harness plugin for Claude Code.

---

## 1. Introduction

### Start from one fundamental question

When you ask an LLM to write code, **the model itself is fixed**. The same model produces reliable engineering for one person and "looks-like-it-runs, actually-full-of-holes" code for another. The difference usually isn't the model — it's **everything around the model**: what context it sees on startup, what constrains each of its actions, what verification it must pass before it claims "done," and whether errors feed back into a correction.

That "everything around the model" is the **harness**. LangChain, Anthropic, and OpenAI converge on the same definition: the harness is not the model, but the **context management, constraints, verification, and feedback loop surrounding it**. Which leads to a plain but pivotal conclusion:

> **The quality of LLM-assisted development is determined mostly by the harness, not the model.**

Harness Kit starts from exactly this first principle: if the harness is where the leverage is, then turn a good harness into a reusable engineering artifact.

### What Harness Kit is

Harness Kit packages a **reusable, project-agnostic** harness as a Claude Code plugin. A single `/harness-kit:init` gives any repo a self-verifying **Plan → Build → Verify → Done** loop:

- every session starts with git state, active plans, and key docs injected as **handoff context**;
- editing un-planned code **auto-scaffolds a plan**;
- repeated edits to the same file inject a "reconsider your approach" nudge;
- around context compaction it **snapshots and re-injects** "which plan is unfinished, which verification didn't pass," so the contract survives;
- when you claim "done," a Stop hook runs your verification gates + plan-DoD check, and **premature "done" gets blocked**;
- on demand, it dispatches an **independent evaluator** — fresh context, write-tools disabled — that scores the change against your rubric.

### What pain it solves

LLM-assisted development broadly lacks an **automatic, configurable, end-to-end** engineering-check framework spanning from session start to the "done" claim. Claude Code natively provides hook **events** and **injection mechanisms** (SessionStart / UserPromptSubmit `additionalContext`, PreToolUse context, Stop `exit 2`, PreCompact, PostToolUse, Setup), but **none of the content behaviors** — no multi-gate verification orchestration, no loop detection, no plan persistence, no context snapshot. Harness Kit supplies exactly those, wired through the native events.

### Who it's for

Individuals and teams using Claude Code who want output that can be **verified** rather than merely "looks like it runs." Two presets ship in the box — **godot** and **web** — plus **custom** for any project.

---

## 2. Design Philosophy

Every principle is derived from the thesis above, in a **Problem → Reasoning → Implementation** form.

### 1. Project-agnostic: zero project literals in plugin code
- **Problem**: a harness that hard-codes one project's paths and commands can only ever serve that one project.
- **Reasoning**: to be reusable across repos, "project-specific" must be cleanly separated from "mechanism."
- **Implementation**: everything project-specific (file globs, verify commands, layering rules, capability switches) lives in a single per-project `.harness/config.json`; the plugin code contains no project literals and never branches on project type at runtime.

### 2. Inert until initialized: zero side effects on install
- **Problem**: a plugin that changes behavior the moment it's installed makes people afraid to install it.
- **Reasoning**: installing should, in itself, have no side effects.
- **Implementation**: with no `.harness/config.json`, every hook is a no-op (`exit 0`). Installing Harness Kit on an un-initialized repo changes nothing.

### 3. Capabilities are user-owned, not auto-routed
- **Problem**: a "smart" auto-router decides for you when to tighten or loosen verification — but its judgment may be wrong, and it's opaque.
- **Reasoning**: the harness is scaffolding; it evolves and is eventually torn down as the project matures — that cadence should be in human hands.
- **Implementation**: `enabledCapabilities{}` is a set of **switches you own** (`planGate`, `loopDetection`, `toolTrace`, `evaluator`, `contextSnapshot`, plus experimental `evaluatorAutoDispatch`). You toggle them directly; the tool only **suggests**, never **forces**.

### 4. "Done" is a gate, not a claim
- **Problem**: an LLM will readily declare "I'm finished" while tests fail and the plan's acceptance items are unchecked.
- **Reasoning**: "done" must be **earned**, not **declared**.
- **Implementation**: on every completion claim, the Stop hook runs the blocking gates from config + checks active-plan DoD; in `strict` mode any failure means `exit 2`, blocking that completion. (This is the so-called "Ralph Loop.")

### 5. Generator/Evaluator separation
- **Problem**: letting the author grade their own code is both biased and prone to self-rationalization.
- **Reasoning**: the judge shouldn't be the producer.
- **Implementation**: the evaluator is an **independent subagent** — fresh context, Write/Edit disabled — that can only score against the rubric and advise, never fix. Any dimension < 3 = FAIL.

### 6. Contracts must survive context compaction
- **Problem**: long sessions trigger compaction, after which "which plan is unfinished, which gate failed" is easily lost.
- **Reasoning**: these are contracts that must persist; they can't evaporate just because of compaction.
- **Implementation**: `PreCompact` snapshots the current plan / unchecked DoD / failed gate to `.harness/state/`; the next `UserPromptSubmit` afterward (and `SessionStart` on resume) re-injects it once. (PostCompact injection isn't officially supported, so this is the documented path.)

### 7. Cross-platform: a single core + ultra-thin launchers
- **Problem**: logic scattered across per-platform shell scripts is hard to test and hard to port.
- **Reasoning**: logic should live in one place — unit-testable and cross-platform.
- **Implementation**: every `bin/harness-*` and `scripts/run-hook` is an ultra-thin Bash launcher that only locates a Python interpreter and forwards; the real logic lives in a single Python core (`scripts/harness/`), one codebase running natively on macOS / Linux / Windows (with forced UTF-8 and cross-platform process checks).

### 8. Trace-driven self-tuning — advisory, never forced
- **Problem**: a gate configured long ago may have become useless without anyone noticing.
- **Reasoning**: tuning should be **evidence-based** and respect the user's final judgment.
- **Implementation**: every gate / evaluator run is recorded to `trace.jsonl`; `/harness-kit:trace-analyze` analyzes it (e.g. "gate X caught 0 issues in 10 runs — consider disabling") and **suggests** — you decide whether to change anything.

> The philosophy in one line: **the harness is scaffolding meant to be torn down as the project matures — so capabilities are switches you own, not an auto-router that decides for you.**

---

## 3. Usage

### Requirements

| Platform | Required |
|---|---|
| **macOS / Linux** | `python3` (≥3.9) and `git` — both usually preinstalled. |
| **Windows** | [Git for Windows](https://gitforwindows.org/) (provides `git` + Git Bash) and [Python 3](https://www.python.org/downloads/windows/) (≥3.9 — make sure `python` or `py -3` is on PATH). Claude Code runs hooks via Git Bash on Windows, so **WSL is not required**. |

> The CI matrix passes on macOS / Ubuntu / Windows × Python 3.9 and 3.12.

### Install

```
/plugin marketplace add whieet/harness-kit
/plugin install harness-kit@harness-kit
```

### Initialize

```
/harness-kit:init [godot|web|custom]
```

Detect or ask the project type → scaffold `.harness/config.json` + rubric + plan/docs skeleton → enable the git pre-commit gate. Idempotent; `--force` resets. Until initialized, the plugin is fully inert.

### Lifecycle: which events the harness hooks into

| Claude Code event | Harness behavior |
|---|---|
| **SessionStart** | Inject handoff: git state, active plans, enabled capabilities, key docs. |
| **PreToolUse** (Edit / Write) | Plan gate: editing a file matching `plan.codeGlob` with no plan auto-scaffolds one. |
| **PostToolUse** (ExitPlanMode) | Persist the approved plan as an active plan. |
| **PostToolUse** (Edit) | Loop detection: at the edit threshold for one file, nudge "reconsider your approach." |
| **PreCompact** | Snapshot current plan / unchecked DoD / failed gate to `.harness/state/`. |
| **UserPromptSubmit** | Re-inject the snapshot once after compaction. |
| **Stop** | Pre-completion gate: run blocking gates + check DoD; in `strict`, failure means `exit 2`, blocking "done." |

### Commands

| Command | What it does |
|---|---|
| `/harness-kit:init [godot\|web\|custom]` | Detect/ask project type, scaffold config + rubric + skeleton, enable the git gate. |
| `/harness-kit:plan` | Enter plan mode seeded with the project plan template. |
| `/harness-kit:verify` | Run the config-driven gate orchestrator and report per-gate pass/fail. |
| `/harness-kit:evaluate` | Dispatch the independent evaluator subagent to score the current change (any dimension < 3 = FAIL). |
| `/harness-kit:advisor` | Passive dashboard: artifact counts, enabled capabilities, configured gates, trace suggestions. |
| `/harness-kit:trace-analyze` | Analyze the harness's own trace and suggest gate / config tuning. |

> Also: `claude -p --maintenance` runs `harness-maintenance` (migrate legacy config `phases[]` → `enabledCapabilities{}`, repair state).

### Configuration: `.harness/config.json`

Plugin code has zero project literals; everything project-specific lives in this one git-tracked file. Key fields:

- `gates[]` — verification gates (name, command, blocking / tier, skip conditions)
- `layeringRules[]` — architecture layering rules (scope glob, forbidden regex, remediation)
- `plan` — plan conventions (directory, `codeGlob`, status field, DoD regex)
- `docs` — key docs, scan roots, architecture-drift checks
- `metrics[]` — artifact counts (docs, completed plans, etc.)
- `enabledCapabilities{}` — capability switches (see Design Philosophy #3)
- `effortRouting` — opt-in Reasoning Sandwich: low/medium-effort turns run only `tier:"fast"` gates (skips are logged, never silent); high+ runs everything; **off by default**
- `evaluator` / `verificationRecipe` — evaluator rubric path and dimension → check mapping
- `verificationMode` — `advisory` (warn only) or `strict` (`exit 2` to block)

See `templates/config.schema.json` for the full key reference; the presets in `templates/godot/` and `templates/web/` are the fastest way to understand a real config.

### Project layout at a glance

```
scripts/harness/      Python core (all logic for hooks/ and commands/)
scripts/run-hook      bash hook launcher (locate Python, forward)
bin/harness-*         ultra-thin bash command launchers
hooks/hooks.json      Claude Code hook-event declarations
templates/            config schema, plan template, godot / web presets
skills/               6 slash-command frontends (init / plan / verify / evaluate / advisor / trace-analyze)
agents/evaluator.md   independent evaluator subagent definition
```

---

## Migrating an existing hand-rolled harness

Install the plugin → `/harness-kit:init <type>` to generate an equivalent `.harness/config.json` → confirm `/harness-kit:verify` reproduces your old gate results on a known-clean and a known-dirty commit → delete the old scripts and remove the `hooks` block from `.claude/settings.json`. Already on an older Harness Kit config? Run `claude -p --maintenance` to migrate `phases[]` → `enabledCapabilities{}`.

## Optional composables (not dependencies)

Harness Kit is **self-contained**. These marketplace plugins *complement* it but don't replace its core: **claude-mem** (durable cross-session memory), **code-review** (official, pre-push diff review), **security-guidance** (official, security scanning).

## License

MIT — see `LICENSE`.
