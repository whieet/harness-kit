---
name: evaluate
description: Dispatch the skeptical evaluator subagent to score the current change against the project rubric (Generator/Evaluator separation). Use before declaring a coding task done, or when the Stop gate recommends it.
---

# /harness-kit:evaluate

Run an INDEPENDENT evaluation of the current change — the robust path for
Generator/Evaluator separation (a generator grading itself is unreliable).

## Steps

1. **Dispatch the `evaluator` subagent** (via the Task/Agent tool, subagent type `evaluator`). It runs with fresh context and has no edit tools, so it cannot grade its own work. Tell it what changed (the current diff scope / the active plan).

2. The evaluator will: read `.harness/rubric.md` + `config.verificationRecipe`, run each dimension's verification check (the project's MCP tools / test runners), score every dimension 1–5 (**any dimension < 3 = FAIL**), append its scores to `.harness/state/trace.jsonl` (feeds the config suggester), and return a `VERDICT: PASS | WARN | FAIL`.

3. **Relay** the verdict. On `FAIL`, list the must-fix items and **do not declare the task done** — revise and re-evaluate. On `WARN`, pass but note the technical debt.

## Notes
- This is the recommended, robust evaluator path. An optional **experimental** auto-fire variant (a `type:agent` Stop hook) exists in `hooks/optional-auto-eval.json` — it is context-only (cannot block), runs every Stop, and is off by default; see the README before enabling it.
- The Stop-hook completion gate (`harness-verify` + plan DoD) remains the hard, blocking gate; the evaluator is the subjective-quality layer on top.
