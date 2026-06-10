<div align="center">

# Harness Kit

**Project-agnostic *harness engineering* for [Claude Code](https://claude.com/claude-code)**

Weaves plan-gating, pre-completion verification, loop detection, and Generator / Evaluator separation directly into your AI coding workflow.

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-d97757)](https://claude.com/claude-code)
[![Version](https://img.shields.io/badge/version-0.1.2-2ea44f)](./.claude-plugin/plugin.json)
[![CI](https://github.com/whieet/harness-kit/actions/workflows/test.yml/badge.svg)](https://github.com/whieet/harness-kit/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

**English** · [简体中文](./README.md)

</div>

> The Simplified Chinese [README.md](./README.md) is the authoritative version; this English page mirrors it.

---

## What it is

Harness Kit is a **Claude Code plugin** (built for Claude Code — **not codex or other CLIs**). Using Claude Code's hooks / slash commands / subagents / skills, it adds automatic guardrails at the critical moments of AI coding: there must be a plan before you edit, the verification gate must pass before you finish, repeated edits to the same file raise a warning, and final quality is scored by an independent evaluator subagent.

Everything project-specific (verify commands, layering rules, plan directory, doc paths, metrics…) lives in each project's own `.harness/config.json` — the plugin code itself is **project-agnostic**, so the same harness applies to Godot, web, or any custom stack.

## Why you need it

Harness Kit is built to stop the common ways AI coding goes off the rails:

- **Editing without a plan** — large changes lack a Definition of Done and drift.
- **Finishing without verifying** — declaring "done" without running lint / build / test.
- **Self-grading bias** — letting the generator score its own work is unreliable.
- **Lost context** — plans and progress vanish after a long session is compacted.
- **Doc / code drift** — docs slowly diverge from the implementation, links rot.

## Core disciplines

| Discipline | What it does |
| --- | --- |
| Plan-gating | A code edit needs a covering plan first; otherwise a plan skeleton is scaffolded for you |
| Verification gate | On Stop, runs the gates configured in `harness-verify`; in strict mode a failure blocks completion |
| Loop detection | Warns when a single file is edited past the threshold (default 5) in one session, preventing churn |
| Gen · Eval separation | Dispatches an edit-less `evaluator` subagent to score against the rubric — no self-grading |
| Context survival | Snapshots plans / progress before compaction and re-injects after, so long sessions keep state |
| Layering | Checks illegal cross-layer references against configurable dependency-direction rules |
| Doc coherence | Validates plan status, naming, placeholder content, dead links, and architecture drift |
| Effort routing | Low/medium-effort turns run only `fast`-tier gates (optional, off by default — never silently weakens verification) |
| Capability toggles | Every harness behavior can be switched on/off individually in config — you stay in control |

## Quick start

> Prerequisite: [Claude Code](https://claude.com/claude-code). Harness Kit is a Claude Code plugin and is enabled by default once installed.

**1) Install the plugin** (type inside Claude Code)

```text
/plugin marketplace add whieet/harness-kit
/plugin install harness-kit@harness-kit
```

**2) Initialize it in your project**

```text
/harness-kit:init
```

Pick a project type (`godot` / `web` / `custom`). It scaffolds `.harness/config.json` + `rubric.md` + a plan directory and enables the git pre-commit gate. Idempotent; pass `reset` to overwrite.

**3) Code as usual** — PreToolUse / PostToolUse hooks apply guardrails automatically (plan gate, loop detection, tracing); nothing to trigger manually.

**4) Finish** — the Stop hook runs the verification gate; in strict mode a failure blocks "done".

## Slash commands

| Command | What it does |
| --- | --- |
| `/harness-kit:init` | Initialize: detect / ask project type, scaffold config + rubric + plan skeleton, enable the pre-commit gate |
| `/harness-kit:plan` | Start the Plan→Build→Verify→Done workflow; on approval a hook persists the plan to the plan directory |
| `/harness-kit:verify` | Run the verification-gate orchestrator and report per-gate pass / fail (manual counterpart to the Stop gate) |
| `/harness-kit:advisor` | Show the current maturity phase, the artifact metrics behind it, and which harness capabilities are unlocked |
| `/harness-kit:evaluate` | Dispatch the skeptical `evaluator` subagent to score the current change against the rubric |
| `/harness-kit:trace-analyze` | Analyze the session trace for failure patterns (pass rate, session imbalance, high-churn files) and suggest tuning |

## Everyday workflow

```mermaid
flowchart LR
    A["/init<br/>one-time scaffold"] --> B["/plan"]
    B --> C["code<br/>hook guardrails"]
    C --> D["/verify<br/>gate"]
    D --> E["/evaluate<br/>independent score"]
    E --> F["finish<br/>Stop gate"]
    F -. "/advisor · /trace-analyze tuning" .-> B
```

After a one-time init, a typical task flows like this (〔auto〕= happens via hooks, 〔manual〕= you type a command):

1. **Session start** 〔auto〕— SessionStart injects a handoff: git state, in-progress plans, the advisor dashboard, key docs — so Claude immediately picks up "where it left off".
2. **Plan** 〔manual · non-trivial change〕— `/harness-kit:plan` enters plan mode; once you approve, a hook persists the plan and starts tracking its DoD. Skip for small edits.
3. **Code** 〔auto guardrails〕— before each edit, checks the file is covered by a plan (scaffolds a skeleton if not); after each edit, increments the loop counter and warns on excessive churn; tool calls are written to the trace.
4. **Spot-check** 〔manual · optional〕— `/harness-kit:verify` to run the gates, `/harness-kit:advisor` to see phase and capabilities.
5. **Finish gate** 〔auto · can block〕— Stop runs the verification gates + uncommitted check + plan-DoD self-check; in strict mode a failure blocks "done" and prompts more fixes.
6. **Independent eval** 〔manual · optional〕— before declaring done, `/harness-kit:evaluate` dispatches the edit-less `evaluator` to score against the rubric, avoiding self-grading.
7. **Context survives** 〔auto〕— on compaction, plans/progress are snapshotted and re-injected on the next message, so state carries over.
8. **Periodic tuning** 〔manual · occasional〕— `/harness-kit:trace-analyze` surfaces failure patterns to fine-tune `.harness/config.json`.

> Steps 1 / 3 / 5 / 7 are fully automatic — you barely think about them; the only commands you actually reach for are `plan` / `verify` / `evaluate` / `advisor`.

## Configuration at a glance

Everything project-specific lives in `.harness/config.json` (committed with your project). Key sections:

| Section | Meaning |
| --- | --- |
| `gates[]` | Ordered verification gates run by `harness-verify` (replaces hardcoded steps) |
| `verifyCmd` / `buildCmd` / `testCmd` | Verify / build / test entrypoint commands |
| `layeringRules[]` | Dependency-direction constraints (scope glob + forbidden regex + remediation hint) |
| `plan` | Plan lifecycle: directory, which edits require a plan (`codeGlob`), status field, template |
| `docs` | Key docs, scan roots, architecture path, staleness thresholds, placeholder / drift detection |
| `metrics[]` | Artifact counts (by glob) — input to the advisor dashboard |
| `enabledCapabilities` | Per-behavior switches: `planGate` / `loopDetection` / `toolTrace` / `evaluator` / `contextSnapshot`, etc. |
| `effortRouting` | Effort-routing (Reasoning Sandwich) switch |
| `evaluator` / `verificationRecipe` | Gen / Eval separation; maps each rubric dimension to a verify command or MCP tool |

See [`templates/config.schema.json`](./templates/config.schema.json) for the full field reference.

## Project presets

`/harness-kit:init` ships three scaffolds (see [`templates/`](./templates)):

- **godot** — Godot games: headless compile gate, layering rules, and a rubric with gameplay / visual / integration / quality dimensions.
- **web** — React / Vue / Vite / Next / Svelte: npm lint / test / build gates, and a rubric with UX / integration / quality dimensions.
- **custom** — Your own stack, no preset; fill in `.harness/config.json` as needed.

## Requirements

- **Claude Code** — this is a Claude Code plugin and relies on its hooks / slash-command / subagent runtime; **not for codex or other CLIs**.
- **Python 3.9+** — the core logic is Python; `bin/` holds thin launchers.
- **Platforms** — macOS / Linux / Windows (Windows runs via Git Bash).

## License

[MIT](./LICENSE) © River
