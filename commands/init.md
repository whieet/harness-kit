---
description: Initialize harness-kit in the current project. Detects or asks the project type (godot | web | custom), scaffolds .harness/config.json + rubric + plan/docs skeleton, and enables the git pre-commit gate. Idempotent; pass "reset" to overwrite an existing config.
---

# /harness-kit:init

Set up the harness in this repository. Be careful and idempotent — never clobber a
user's existing `.harness/config.json` unless they explicitly ask to reset.

## Steps

1. **Decide the project type.**
   - If the user's message names a type (`godot`, `web`, or `custom`), use it.
   - Otherwise probe the repo:
     - `test -f project.godot` → **godot**
     - `test -f package.json` and it depends on react/vue/vite/next/svelte (grep `package.json`) → **web**
   - If exactly one matches, state the detected type and proceed.
   - If **both or neither** match, ask the user with the AskUserQuestion tool: `godot | web | custom`. Do not silently guess.

2. **Run the scaffolder** (it does all file writes deterministically and idempotently):
   ```bash
   harness-init <type>
   ```
   Add `--force` only if the user explicitly asked to reset/overwrite an existing config.
   - `harness-init` is on PATH (bundled in the plugin's `bin/`). If the shell can't find it, the plugin may not be enabled — tell the user to run `/plugin install harness-kit`.

3. **Report** what it wrote: the config path, the project type, the gates that will run (read them back from `.harness/config.json`), and the next command: `/harness-kit:verify`.

4. **Tune (for `custom`, or to adapt a preset).** Open `.harness/config.json` and confirm with the user:
   - `gates[]` — the verification commands (lint/typecheck/build/test) for their stack.
   - `layeringRules[]` — their architecture's forbidden dependencies.
   - `plan.codeGlob` — which file types require a plan before editing.
   - `verificationRecipe` — which runtime tool checks each evaluator dimension.
   The full key reference is `${CLAUDE_PLUGIN_ROOT}/templates/config.schema.json`.

## Notes

- The plugin is **inert until this runs** — with no `.harness/config.json`, every hook is a no-op.
- `.harness/config.json` and `.harness/rubric.md` are meant to be **committed** (project config). The `.harness/state/` dir (loop counters, trace) is gitignored automatically.
- The git pre-commit gate is wired via `git config core.hooksPath .harness/hooks`. If the project already uses a custom hooks path, mention the conflict instead of overwriting silently.
