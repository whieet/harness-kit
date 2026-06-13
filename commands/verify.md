---
description: Run the project's harness verification gates (the config-driven harness-verify orchestrator) and report per-gate pass/fail. The manual counterpart to the automatic Stop-hook gate. Use to check work mid-task before declaring done.
---

# /harness-kit:verify

Run the verification gate orchestrator and report results.

## Steps

1. Read `.harness/config.json` first and follow its `language` preference when reporting results. Do not translate file/directory names, command names, or config keys.

2. Run it:
   ```bash
   harness-verify
   ```
   This reads `.harness/config.json` → `gates[]` and runs each in order, aggregating a single pass/fail. Blocking gates that fail cause a non-zero exit; soft gates only warn.

3. **Report** clearly:
   - If it exits 0: say which gates passed (and note any soft warnings).
   - If it exits non-zero: show the failing gate(s) and their output, and propose the concrete fix. Do not declare the task done until `harness-verify` is green.

4. If the project isn't initialized (`harness-verify` says no config), suggest `/harness-kit:init`.
