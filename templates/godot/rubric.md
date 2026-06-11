# Evaluator Rubric — Godot

Score each dimension **1–5** against the active plan's requirements (not against
what the code claims). **Any dimension < 3 = FAIL.** Use the `verificationRecipe`
in `.harness/config.json` to gather evidence — run the MCP tools, read full output.

## 1. Functionality (hard gate)
- Run the affected scene via your Godot MCP server: it starts without crashing.
- No runtime/script errors (check the editor-errors tool).
- The changed behavior actually works as the plan specifies (drive it via input simulation / script execution).
- 5 = all paths incl. empty/error states verified; 3 = happy path verified; 1 = crashes or no evidence.

## 2. Visual / UX
- Screenshot the affected scene: layout is complete and not broken.
- Diff against a screenshot baseline (if you keep one): no unintended regression.
- New elements match the existing visual language (see your design doc, e.g. `docs/DESIGN.md`).
- 5 = pixel-consistent + on-spec; 3 = acceptable, minor polish debt; 1 = visibly broken.

## 3. Integration
- Your app's existing features and flows still work.
- Your autoloads' signals are wired correctly (event bus / registry pattern — verify via node-state / signal assertions).
- 5 = no regressions, signals verified; 3 = no obvious regression; 1 = breaks existing flows.

## 4. Code quality
- `harness-verify` exits 0 (layering + headless compile).
- No hardcoded paths, no debug leftovers, respects the layering direction.
- 5 = clean, idiomatic, documented; 3 = works but has debt; 1 = layering violation or dead code.

## Verdict
- PASS = every dimension ≥ 3. WARN = all ≥ 3 with some == 3 (flag debt). FAIL = any < 3 (list fixes).
