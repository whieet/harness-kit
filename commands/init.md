---
description: Initialize harness-kit in the current project. Detects or asks the project type (godot | web | custom), scaffolds .harness/config.json + rubric + plan/docs skeleton + a ToC-style CLAUDE.md when the project has none, and enables the git pre-commit gate; then analyzes the codebase to fill in the blanks and tune the config. Idempotent; pass "reset" to overwrite an existing config.
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
   - Add `--force` only if the user explicitly asked to reset/overwrite an existing config.
   - Add `--lang zh` to scaffold the CLAUDE.md constitution in Chinese — pick the language the user is working in (default: English). Add `--no-claude-md` if the user doesn't want one.
   - `harness-init` is on PATH (bundled in the plugin's `bin/`). If the shell can't find it, the plugin may not be enabled — tell the user to run `/plugin install harness-kit`.

3. **Report** what it wrote: the config path, the project type, whether a CLAUDE.md constitution was scaffolded, the gates that will run (read them back from `.harness/config.json`), and the next command: `/harness-kit:verify`.

4. **Analyze the codebase & fill in.** Bounded analysis — harness-scoped facts only, not a full audit:
   - Probe for real commands and structure: read `package.json` scripts / `project.godot` / `Makefile` for the actual build/test commands and framework version; list the top two levels of the source tree to see the real layers; scan `docs/` and the repo root for existing docs (README, ARCHITECTURE, DESIGN).
   - **If init printed `wrote CLAUDE.md`** — fill its `(fill in: ...)` markers with what you found (architecture/design doc paths in the repo map; build/run/test commands and stack in Project facts). Stay within the line budget noted at the top of the file; anything bigger belongs in `docs/`, not the constitution. Do NOT inline a general codebase analysis — that is the built-in `/init` command's job, and it composes fine with this file (it improves, it doesn't overwrite).
   - **If init printed `CLAUDE.md exists — keeping`** (the config and rubric print similar "exists — keeping" lines — match the full line) — read the existing CLAUDE.md; if it has no pointer to the harness workflow at all, ask the user before appending 3-5 lines (`.harness/config.json`, the plan dir, `harness-verify`). Never rewrite their content.
   - **Tune `.harness/config.json` to the real project** (confirm with the user before writing):
     - `buildCmd` / `testCmd` — the actual commands you found.
     - `gates[]` — the verification commands (lint/typecheck/build/test) for their stack.
     - `layeringRules[]` — rewrite scope globs to directories that actually exist; drop rules whose scopes match nothing.
     - `plan.codeGlob` — the file types this project actually edits.
     - `metrics[]` / `docs.keyDocs` — point at paths that exist.
     - `verificationRecipe` — which runtime tool checks each evaluator dimension.
   The full key reference is `${CLAUDE_PLUGIN_ROOT}/templates/config.schema.json`.

## Notes

- The plugin is **inert until this runs** — with no `.harness/config.json`, every hook is a no-op.
- `.harness/config.json` and `.harness/rubric.md` are meant to be **committed** (project config). The `.harness/state/` dir (loop counters, trace) is gitignored automatically.
- The scaffolded `CLAUDE.md` is **user-owned**: re-running init keeps it as-is, and even `--force` won't touch it (`--force` only resets plugin-owned config/rubric). Delete it manually if you want a fresh scaffold.
- The git pre-commit gate is wired via `git config core.hooksPath .harness/hooks`. If the project already uses a custom hooks path, mention the conflict instead of overwriting silently.
