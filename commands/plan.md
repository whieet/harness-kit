---
description: Start the Plan→Build→Verify→Done workflow for a non-trivial change. Enters plan mode seeded with the project's plan template; on approval, the ExitPlanMode hook persists the plan into the configured plan directory. Use before any change larger than ~20 lines or touching planned code paths.
---

# /harness-kit:plan

Drive a disciplined plan for the requested change.

## Steps

1. Read the project plan template (`<plan.dir>/_template.md`, where `plan.dir` comes from `.harness/config.json`) so your plan matches the project's expected structure and Definition-of-Done format.

2. Investigate enough to plan well: search for existing utilities/patterns to reuse, identify the files to change, and consider edge cases (empty/error states, performance, regressions).

3. **Enter plan mode** and present a plan with: Context (why), the approach, the affected files, step-by-step actions with their verification method, and a Definition of Done whose items are checkable.

4. On approval, the `on-plan-approved` hook automatically writes the plan into `<plan.dir>/active/`. As you implement, check off the DoD items — the Stop-hook gate verifies them before you can finish, and `harness-check-plan-dod` reminds you to archive the plan to `completed/` when done.

## Notes
- For changes ≤ ~20 lines with no interface change, a full plan is optional — but still run `/harness-kit:verify` before declaring done.
- If you edit planned code (`plan.codeGlob`) with no covering plan, the plan-gate hook auto-scaffolds one for you to fill in.
