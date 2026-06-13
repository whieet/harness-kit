---
name: advisor
description: Show the project's current harness maturity phase, the artifact metrics behind it, and which harness capabilities are unlocked. Use at session start or when deciding whether to adopt heavier harness practices (evaluator, golden regression, etc.).
---

# /harness-kit:advisor

Report the current maturity phase and unlocked capabilities.

## Steps

1. Read `.harness/config.json` first and follow its `language` preference when explaining the advisor output. Do not translate file/directory names, command names, or config keys.

2. Run it:
   ```bash
   harness-advisor
   ```
   This counts the configured `metrics[]` globs and selects the first matching phase from `phases[]` (highest priority first), printing the metric panel, the current phase, and its unlocked capabilities.

3. **Relay** the phase and capabilities to the user. If the project just crossed into a new phase, point out the newly-available capabilities and suggest starting to use them (e.g. dispatching the `evaluator` subagent once you reach a multi-feature phase).

4. If no phase matches or metrics look wrong, the `metrics[]`/`phases[]` in `.harness/config.json` likely need tuning — offer to adjust them.
