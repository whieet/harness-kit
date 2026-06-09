# Evaluator Rubric — Godot

Score each dimension **1–5** against the active plan's requirements (not against
what the code claims). **Any dimension < 3 = FAIL.** Use the `verificationRecipe`
in `.harness/config.json` to gather evidence — run the MCP tools, read full output.

## 1. Functionality (hard gate)
- `play_scene`: the affected scene starts without crashing.
- `get_editor_errors`: no runtime/script errors.
- The changed behavior actually works as the plan specifies (drive it via input simulation / `execute_game_script`).
- 5 = all paths incl. empty/error states verified; 3 = happy path verified; 1 = crashes or no evidence.

## 2. Visual / UX
- `get_game_screenshot`: layout is complete and not broken.
- `compare_screenshots` vs `tests/golden/`: no unintended regression.
- New elements match the existing visual language (see `docs/DESIGN.md`).
- 5 = pixel-consistent + on-spec; 3 = acceptable, minor polish debt; 1 = visibly broken.

## 3. Integration
- Existing features still work (desktop / taskbar / chat / file manager as applicable).
- `AppRegistry` / `EventBus` signals wired correctly (`assert_node_state` / `watch_signals`).
- 5 = no regressions, signals verified; 3 = no obvious regression; 1 = breaks existing flows.

## 4. Code quality
- `harness-verify` exits 0 (layering + headless compile).
- No hardcoded paths, no debug leftovers, respects the layering direction.
- 5 = clean, idiomatic, documented; 3 = works but has debt; 1 = layering violation or dead code.

## Verdict
- PASS = every dimension ≥ 3. WARN = all ≥ 3 with some == 3 (flag debt). FAIL = any < 3 (list fixes).
