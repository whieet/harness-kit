{{IMPORTS}}# CLAUDE.md — Project Constitution

> Scaffolded by harness-kit for a {{PROJECT_TYPE}} project. This file is a table of
> contents, not an encyclopedia — keep it under {{LINE_BUDGET}} lines (enforced by the
> `claude-md-budget` gate). Durable knowledge belongs in `docs/`, not here.

## 1. Iron laws

1. **Plan before non-trivial edits** — a covering plan must exist in `{{PLAN_DIR}}/active/` (start one from `{{PLAN_DIR}}/_template.md`, or let the plan gate scaffold it).
2. **Never declare done unless `harness-verify` exits 0** — it runs the gates in `.harness/config.json` and doubles as the pre-commit hook and Stop gate.
3. **Verification gates and tests must not be deleted or weakened** — add or skip with a written reason; never edit away a failing check.
4. **Knowledge goes into `docs/`** — undocumented agreements do not exist for agents.
5. **Respect the dependency directions** declared in `layeringRules` (`.harness/config.json`).

## 2. Standard workflow — Plan → Build → Verify → Done

| Step | What | Artifact |
|---|---|---|
| Plan | Copy `{{PLAN_DIR}}/_template.md` into `active/`; fill background / goals / steps / Definition of Done | plan file |
| Build | Implement incrementally, following the plan and the layering rules | code |
| Verify | Run `harness-verify` + runtime checks; log results in the plan's progress log; tick DoD items | all green |
| Done | Move the plan to `{{PLAN_DIR}}/completed/` | archive |

> Spend reasoning on Plan and Verify; Build can be cheap. Work in small verified increments.

## 3. Repo map

| Need | Path |
|---|---|
| Current tasks | `{{PLAN_DIR}}/active/` |
| New plan skeleton | `{{PLAN_DIR}}/_template.md` |
| Harness config (gates, layering, plan rules) | `.harness/config.json` |
| Evaluation rubric | `.harness/rubric.md` |
| Architecture | (fill in: path to the architecture doc, e.g. `ARCHITECTURE.md`) |
| Design / product docs | (fill in: paths, or remove this row) |

## 4. Verification SOP

- `harness-verify` — the local gate; also wired as the git pre-commit hook and the Stop gate.
- Runtime verification recipes per dimension live in `verificationRecipe` (`.harness/config.json`).
- For large changes, run `/harness-kit:evaluate` for an independent score against `.harness/rubric.md`.

## 5. Project facts

- Build / run: (fill in: command)
- Test: (fill in: command)
- Stack: (fill in: framework + version, environment quirks worth pinning)

<!-- harness-kit:claude-md v1 -->
