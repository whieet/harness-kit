# Harness Kit

**English** | [中文](README.md)

A **project-agnostic harness-engineering plugin for Claude Code**. It turns any
repo into a self-verifying **Plan → Build → Verify → Done** loop:

- **Session handoff** — every session starts with git state, active plans, enabled capabilities, and key docs injected as context.
- **Plan-gating** — editing un-planned code auto-scaffolds a plan; approving a plan (ExitPlanMode) persists it.
- **Pre-completion verification gate** — a Stop hook runs your project's verification gates + plan-DoD check, blocking premature "done" (exit 2).
- **Independent evaluator** — `/harness-kit:evaluate` dispatches a skeptical, fresh-context subagent that scores the change against your rubric (Generator/Evaluator separation).
- **Loop detection** — repeated edits to the same file inject a "reconsider your approach" nudge.
- **Context management** — before a compaction the harness snapshots which plan / unchecked DoD / failed gate is outstanding, and re-injects it once afterward so the contract survives.
- **Trace-driven self-tuning** — instead of a maturity-phase auto-router, the harness analyzes its own traces and *suggests* config changes ("gate X caught 0 issues in 10 runs — consider disabling"); you decide.

Everything project-specific (file globs, verify commands, layering rules,
verification method, capability switches) lives in a single per-project
**`.harness/config.json`** — the plugin code contains **zero project literals**.
Two ready-made presets ship in the box: **godot** and **web**.

> Design basis: harness engineering as defined by LangChain, Anthropic, and
> OpenAI — the harness is "everything around the model". A core principle is
> *"the harness evolves — tear down scaffolds as the project matures"*, which is
> why capability on/off is user-owned config, not an auto-router.

## Why a plugin (and what's native vs. bundled)

Claude Code natively provides hook **events** and **injection mechanisms**
(SessionStart / UserPromptSubmit `additionalContext`, PreToolUse context, Stop
`exit 2` / `decision:block`, PreCompact, PostToolUse, Setup) — but **none of the
content behaviors** a harness needs: no multi-gate verification orchestrator, no
per-file loop detector, no plan persistence/scaffolding, no doc-drift auditor, no
context snapshot. Harness Kit supplies exactly those, wired through the native
events. (Every mechanism here was verified against the official hooks docs; e.g.
`type:agent` hooks are experimental and **context-only — they cannot block**, so
the blocking gate is always a `type:command` Stop hook.)

## Install

```
/plugin marketplace add river/harness-kit
/plugin install harness-kit@harness-kit
/harness-kit:init           # detects godot|web, or asks; scaffolds .harness/config.json
```

The plugin is **inert until initialized** — with no `.harness/config.json`, every
hook is a no-op, so installing it on an un-initialized repo changes nothing.

## Commands

| Command | What it does |
|---|---|
| `/harness-kit:init [godot\|web\|custom]` | Detect/ask project type, scaffold `.harness/config.json` + rubric + plan/docs skeleton, enable the git pre-commit gate. Idempotent; `--force` resets. |
| `/harness-kit:verify` | Run the config-driven gate orchestrator and report per-gate pass/fail. |
| `/harness-kit:evaluate` | Dispatch the skeptical evaluator subagent to score the current change against the rubric (any dimension < 3 = FAIL). |
| `/harness-kit:advisor` | Passive dashboard: artifact counts, enabled capabilities, configured gates, and trace-driven suggestions. |
| `/harness-kit:plan` | Enter plan mode seeded with the project plan template. |
| `/harness-kit:trace-analyze` | Analyze the harness's own trace for repeated-tool loops, churn, late verification, and gate/evaluator calibration. |

Also: `claude -p --maintenance` runs `harness-maintenance` (migrates legacy
config, repairs state).

## Capabilities, effort routing, context management

- **`enabledCapabilities{}`** — user-owned on/off switches (`planGate`, `loopDetection`, `toolTrace`, `evaluator`, `contextSnapshot`, and experimental `evaluatorAutoDispatch`). This replaces the old maturity-phase auto-router. Toggle them directly; the trace suggester recommends, you decide.
- **`effortRouting`** — opt-in Reasoning Sandwich. When `enabled`, low/medium-effort turns run only `tier:"fast"` gates (skips are logged, never silent); high+ effort runs everything. **Default off** so a low-effort turn never silently weakens verification.
- **Context snapshot** — `PreCompact` writes `.harness/state/pre-compact-snapshot.json`; the next `UserPromptSubmit` re-injects it once (PostCompact injection is not supported, so this is the documented path); `SessionStart` surfaces it on resume.
- **Experimental auto-evaluator** — `hooks/optional-auto-eval.json` is an opt-in `type:agent` Stop hook that auto-runs the evaluator. It is **context-only (cannot block)**, runs every Stop, and is **off by default**. Prefer `/harness-kit:evaluate`.

## Optional composables (not dependencies)

Harness Kit is **self-contained**. These marketplace plugins *complement* it but
do not replace its core (verified: none implement the Stop-hook gate / capability
model / plan lifecycle Harness Kit owns):

- **claude-mem** — durable cross-session memory (Harness Kit's handoff is a lightweight per-session diagnostic).
- **code-review** (official) — `/code-review` as an additive pre-push diff reviewer; slash-triggered, PR-oriented, *not* a Stop-hook gate.
- **security-guidance** (official) — three-layer security scanning where you need security gates.

## Configuration

See `templates/config.schema.json` for the full key reference. The presets in
`templates/godot/` and `templates/web/` are the fastest way to understand a real
config.

## Migrating an existing hand-rolled harness

Install the plugin, run `/harness-kit:init <type>` to generate an equivalent
`.harness/config.json`, confirm `/harness-kit:verify` reproduces your old gate
results on a known-clean and a known-dirty commit, then delete the old scripts
and remove the `hooks` block from `.claude/settings.json`. Already on an older
Harness Kit config? Run `claude -p --maintenance` to migrate `phases[]` →
`enabledCapabilities{}`.

## License

MIT — see `LICENSE`.
