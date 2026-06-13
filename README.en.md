<div align="center">

# Harness Kit

**Project-agnostic *harness engineering* for [Claude Code](https://claude.com/claude-code)**

Weaves plan-gating, pre-completion verification, loop detection, and Generator / Evaluator separation directly into your AI coding workflow.

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-d97757)](https://claude.com/claude-code)
[![Version](https://img.shields.io/badge/version-0.1.3-2ea44f)](./.claude-plugin/plugin.json)
[![CI](https://github.com/whieet/harness-kit/actions/workflows/test.yml/badge.svg)](https://github.com/whieet/harness-kit/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

**English** · [简体中文](./README.md)

</div>

> The Simplified Chinese [README.md](./README.md) is the authoritative version; this English page mirrors it.

---

## What it is

Harness Kit is a **Claude Code plugin** (built for Claude Code — **not codex or other CLIs**). Using Claude Code's hooks / slash commands / subagents / skills, it adds automatic guardrails at the critical moments of AI coding: there must be a plan before you edit, the verification gate must pass before you finish, repeated edits to the same file raise a warning, and final quality is scored by an independent evaluator subagent.

Everything project-specific (verify commands, layering rules, plan directory, doc paths, metrics…) lives in each project's own `.harness/config.json` — the plugin code itself is **project-agnostic**, so the same harness applies to Godot, web, or any custom stack.

## What is harness engineering

A *harness* is **everything around the model** — system prompts, tools, context management, control flow, feedback loops, and memory. **Harness engineering** doesn't touch the model itself; it engineers this scaffolding around the model, molding spiky model intelligence into a reliable, long-running agent.

**Design philosophy** (distilled from public work by OpenAI / Anthropic / LangChain):

- **Leverage is in the harness, not the model** — you can't change the weights, but you can change the scaffolding; architecture choices matter as much as model choice.
- **Separate planning / generation / evaluation** — don't let one agent both do the work and grade itself; self-grading is unreliable, so use an independent evaluator with concrete, measurable criteria.
- **Self-verification loop** — explicit plan → build → test → fix forces the model to actually run tests and verify, instead of stopping at "looks right".
- **Incremental, not one-shot** — on long tasks agents tend to "do it all at once" and declare done prematurely; the harness enforces small steps and end-to-end verification.
- **Continuity across contexts** — context fills up / gets compacted and the agent "forgets"; progress files, memory, and clean handoffs (git commits, state snapshots) carry state across many context windows.
- **Detect bad patterns + budget reasoning** — loop detection and pre-completion checklists catch doom-loops; spend the high reasoning budget where it pays most: planning and verification.

> A harness's assumptions go stale as models improve — trim what newer models handle natively. Harness Kit turns this philosophy into ready-to-use, individually toggleable guardrails inside Claude Code (see [Core disciplines](#core-disciplines)).

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

> [!IMPORTANT]
> **When upgrading an existing install, refresh the plugin-marketplace cache first, then reinstall the plugin.** Otherwise Claude Code may keep using an older local cache, so the README describes a new capability but `/harness-kit:init` does not create `CLAUDE.md` / new gates do not appear. Type inside Claude Code:
> ```text
> /plugin marketplace update harness-kit
> /plugin uninstall harness-kit@harness-kit
> /plugin install harness-kit@harness-kit
> ```
> If an existing project was initialized by an older version, re-running `/harness-kit:init` will create the missing `CLAUDE.md`; however, an existing `.harness/config.json` is not overwritten by default. To adopt new preset gates too, back it up first, then run `/harness-kit:init reset`.

**2) Initialize it in your project**

```text
/harness-kit:init
```

Pick a project type (`godot` / `web` / `custom`) and project language (`en` / `zh`; persisted as `language` in `.harness/config.json`, editable later). It scaffolds `.harness/config.json` + `rubric.md` + a plan directory and enables the git pre-commit gate; if the project has no `CLAUDE.md` yet, it also scaffolds a ToC-style project constitution in the selected language (iron laws / workflow / repo map / verification SOP), then runs a harness-scoped codebase analysis to fill in the blanks and tune the config. An existing `CLAUDE.md` is never touched (not even by `--force`). Pass `--no-claude-md` to skip it. The language preference drives AI interaction and future generated docs; file/directory names, command names, and config keys stay untranslated. Idempotent; pass `reset` to overwrite the config.

**3) Code as usual** — PreToolUse / PostToolUse hooks apply guardrails automatically (plan gate, loop detection, tracing); nothing to trigger manually.

**4) Finish** — the Stop hook runs the verification gate; in strict mode a failure blocks "done".

## Slash commands

| Command | What it does |
| --- | --- |
| `/harness-kit:init` | Initialize: detect / ask project type and language preference, scaffold config + rubric + plan skeleton + a ToC-style CLAUDE.md constitution in the selected language (only when absent), enable the pre-commit gate, then analyze the codebase to fill in the blanks and tune the config |
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

## Make it yours — iterate

The flow above is **one default arrangement, not the right answer**. Harness Kit gives you opinionated defaults and a set of individually toggleable building blocks — **the best harness is *grown***, continuously reshaped around your project, your habits, and the model's evolving abilities. Every behavior is configurable and switchable in `.harness/config.json`, and you **don't hand-write it** — just tell Claude Code in plain language.

Treat the reshaping as its own loop:

1. **Run the defaults first** — after `/harness-kit:init`, resist the urge to tune; do a few real tasks under the default guardrails to build intuition and see what actually chafes.
2. **Observe** — `/harness-kit:advisor` for the maturity phase and unlocked capabilities; `/harness-kit:trace-analyze` for failure patterns (which gates go red, which files churn, whether sessions are imbalanced).
3. **Reshape** (tell Claude Code in plain language; it edits per the [configuration guide](./docs/configuration.en.md)):
   - **Tighten when it derails** — AI went off the rails a new way? Add a gate, a layering rule, or a rubric dimension.
   - **Loosen when it nags** — a gate keeps blocking real work, the loop threshold is too touchy? Turn it off, raise the threshold, or drop `verificationMode` to `advisory`.
   - **Trim as the model improves** — delete disciplines newer models handle natively; a harness's assumptions go stale, and keeping them only slows you down.
4. **Scale with maturity** — start light on new projects (plan gate + verification gate are enough); unlock heavier practices (independent `evaluator`, strict mode, auto-dispatched eval) as features pile up. The advisor flags when to level up.

> There's no "correct" harness — only the one that fits this project right now. Harness Kit hands you the building blocks and one default arrangement; you iterate the workflow into its final shape, and it evolves alongside the model.

## Configuration at a glance

Everything project-specific lives in `.harness/config.json` (committed with your project). **You usually don't hand-write it — just tell Claude Code what you want in plain language** ("add an `npm test` gate", "turn off loop detection", "forbid the UI layer from importing the DB") and it edits the file per the AI-oriented [configuration guide](./docs/configuration.en.md). Key sections:

| Section | Meaning |
| --- | --- |
| `gates[]` | Ordered verification gates run by `harness-verify` (replaces hardcoded steps) |
| `language` | Project language preference: AI interaction and generated docs use `en` / `zh`; file names, directory names, command names, and config keys stay untranslated |
| `verifyCmd` / `buildCmd` / `testCmd` | Verify / build / test entrypoint commands |
| `layeringRules[]` | Dependency-direction constraints (scope glob + forbidden regex + remediation hint) |
| `plan` | Plan lifecycle: directory, which edits require a plan (`codeGlob`), status field, template |
| `docs` | Key docs, scan roots, architecture path, staleness thresholds, placeholder / drift detection |
| `metrics[]` | Artifact counts (by glob) — input to the advisor dashboard |
| `enabledCapabilities` | Per-behavior switches: `planGate` / `loopDetection` / `toolTrace` / `evaluator` / `contextSnapshot`, etc. |
| `effortRouting` | Effort-routing (Reasoning Sandwich) switch |
| `evaluator` / `verificationRecipe` | Gen / Eval separation; maps each rubric dimension to a verify command or MCP tool |

For full fields, annotated examples, and "user says → how to change it" recipes, see the [**configuration guide**](./docs/configuration.en.md) (written for the AI, handy for humans too); the machine-readable schema is [`templates/config.schema.json`](./templates/config.schema.json).

## Project presets

`/harness-kit:init` ships three scaffolds (see [`templates/`](./templates)):

- **godot** — Godot games: headless compile gate, layering rules, and a rubric with gameplay / visual / integration / quality dimensions.
- **web** — React / Vue / Vite / Next / Svelte: npm lint / test / build gates, and a rubric with UX / integration / quality dimensions.
- **custom** — Your own stack, no preset; fill in `.harness/config.json` as needed.

All three presets share one bilingual CLAUDE.md constitution template ([`claude-md-template.en.md`](./templates/claude-md-template.en.md) / [`claude-md-template.zh.md`](./templates/claude-md-template.zh.md)) — generic harness engineering discipline; project facts are filled in by the post-init codebase analysis.

## Requirements

- **Claude Code** — this is a Claude Code plugin and relies on its hooks / slash-command / subagent runtime; **not for codex or other CLIs**.
- **Python 3.9+** — the core logic is Python; `bin/` holds thin launchers.
- **Platforms** — macOS / Linux / Windows (Windows runs via Git Bash).

## Testing & quality

A four-layer test pyramid: unit/parity (L1) → structure + full-session replay e2e (L2, no model calls) → a **real headless Claude** scenario suite (L3, one live scenario per discipline) → a **3-judge AI conformance audit** (L4) against 17 principles distilled from the [references](#references--further-reading).

```bash
python3 -m pytest tests              # L1+L2, free; CI runs it on push to main / PRs, all platforms
claude plugin validate . --strict    # strict manifest validation, free
bash scripts/dev-e2e.sh full         # L3+L4: 6 scenarios + the 3-judge audit (real Claude)
```

See the [testing guide](./docs/testing.en.md).

## References & further reading

Harness Kit's approach distills and pays homage to the following public work — the "knowledge sources" behind this repo's harness engineering:

- **OpenAI** — [Harness Engineering](https://openai.com/index/harness-engineering/)
- **Anthropic** — [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **Anthropic** — [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **LangChain** — [The anatomy of an agent harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness)
- **LangChain** — [Improving deep agents with harness engineering](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)

## License

[MIT](./LICENSE) © River
