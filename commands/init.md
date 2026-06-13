---
description: Initialize harness-kit in the current project. Detects or asks the project type (godot | web | custom) and language (en | zh), scaffolds .harness/config.json + rubric + plan/docs skeleton + a ToC-style CLAUDE.md when the project has none, and enables the git pre-commit gate; then analyzes the codebase to fill in the blanks and tune the config. Idempotent; pass "reset" to overwrite an existing config.
---

# /harness-kit:init

Set up the harness in this repository. Be careful and idempotent — never clobber a
user's existing `.harness/config.json` unless they explicitly ask to reset.

## Steps

1. **Ask for the project language first.**
   - If the user's message explicitly includes `--lang en`, `--lang zh`, English/`en`, or Chinese/中文/`zh`, use that explicit choice.
   - Otherwise **always ask language before any repo probing or project-type question** with the AskUserQuestion tool: `中文 (zh) | English (en)`. Do not infer from the current conversation and do not proceed without a language choice.
   - Once chosen, use that language for every subsequent explanation, question, and generated document in this init flow.
   - This preference is persisted in `.harness/config.json` as `language` and can be changed later. It controls AI-facing guidance and generated document content; file/directory names, command names, and config keys stay untranslated.

2. **Decide the project type using the selected language.**
   - If the user's message names a type (`godot`, `web`, or `custom`), use it.
   - Otherwise probe the repo:
     - `test -f project.godot` → **godot**
     - `test -f package.json` and it depends on react/vue/vite/next/svelte (grep `package.json`) → **web**
   - If exactly one matches, state the detected type in the selected language and proceed.
   - If **both or neither** match, ask the user with the AskUserQuestion tool in the selected language: `custom | godot | web`. Do not silently guess.

3. **Run the scaffolder** (it does all file writes deterministically and idempotently):
   ```bash
   harness-init <type> --lang <en|zh>
   ```
   - Add `--force` only if the user explicitly asked to reset/overwrite an existing config.
   - Add `--no-claude-md` if the user doesn't want a CLAUDE.md constitution.
   - `harness-init` is on PATH (bundled in the plugin's `bin/`). If the shell can't find it, the plugin may not be enabled — tell the user to run `/plugin install harness-kit`.

4. **Report** what it wrote: the config path, the project type, the persisted `language`, whether a CLAUDE.md constitution was scaffolded, the gates that will run (read them back from `.harness/config.json`), and the next command: `/harness-kit:verify`.

5. **Analyze the codebase & fill in.** Bounded analysis — harness-scoped facts only, not a full audit:
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
- The `language` preference lives in `.harness/config.json`; update that field later to switch AI interaction and future generated document content. Do not rename files/directories/commands/config keys when changing language.
- The scaffolded `CLAUDE.md` is **user-owned**: re-running init keeps it as-is, and even `--force` won't touch it (`--force` only resets plugin-owned config/rubric). Delete it manually if you want a fresh scaffold.
- The git pre-commit gate is wired via `git config core.hooksPath .harness/hooks`. If the project already uses a custom hooks path, mention the conflict instead of overwriting silently.
