# Evaluator Rubric — Web Frontend

Score each dimension **1–5** against the active plan's requirements (not against
what the code claims). **Any dimension < 3 = FAIL.** Use the `verificationRecipe`
in `.harness/config.json` to gather evidence — run the tests/tools, read full output.

## 1. Functionality (hard gate)
- The e2e/unit tests for the changed behavior pass (`npx playwright test` / project runner).
- The feature works as the plan specifies, including empty, loading, and error states.
- 5 = all states covered by passing tests; 3 = happy path covered; 1 = failing tests or no evidence.

## 2. Visual / Accessibility
- Playwright screenshot / visual-regression: no unintended layout regression vs baseline.
- Keyboard focus order and basic a11y (labels, roles, contrast) are intact.
- 5 = on-spec + a11y verified; 3 = acceptable, minor polish debt; 1 = broken layout or a11y regressions.

## 3. Integration
- Existing flows still pass their e2e suite (no regression).
- API/contract boundaries respected; no leaking of server concerns into UI.
- 5 = full suite green, boundaries clean; 3 = no obvious regression; 1 = breaks existing flows.

## 4. Code quality
- `harness-verify` exits 0 (eslint + tsc + layering).
- No `any`-escapes hiding real type errors, no console/debug leftovers, no dead code.
- 5 = clean, typed, idiomatic; 3 = works with debt; 1 = lint/type errors or layering violation.

## Verdict
- PASS = every dimension ≥ 3. WARN = all ≥ 3 with some == 3 (flag debt). FAIL = any < 3 (list fixes).
