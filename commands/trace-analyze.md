---
description: Analyze the harness's own session trace for failure patterns — verify pass/fail rate, session imbalance, and high-churn (doom-loop) files. Use periodically to decide how to tune the harness itself (thresholds, gates, reasoning budget).
---

# /harness-kit:trace-analyze

Surface harness-level failure patterns and suggest tuning.

## Steps

1. Read `.harness/config.json` first and follow its `language` preference when explaining findings and proposed tuning. Do not translate file/directory names, command names, or config keys.

2. Run it:
   ```bash
   harness-trace-analyze
   ```
   (add `--json` for machine-readable output). It reads the project-local harness
   state (`.harness/state/trace.jsonl` + `loop-*.json`) and reports session counts,
   completion-gate pass/fail rate, most-churned files, and flagged signals.

3. **Interpret** the signals and propose concrete harness tuning, e.g.:
   - `high_churn` on a file → the loop-detection threshold may be too high, or a gate is missing for that area.
   - `verify_failure_rate` high → gates are catching real problems late; suggest tighter incremental verification or an earlier `/harness-kit:verify` habit.
   - `session_imbalance` → sessions ending abnormally; check for crashes or premature exits.

4. This is the "harness evolves" loop: the goal is to read the trace, then adjust `.harness/config.json` (thresholds, gates, phases) — not to over-fit. Recommend changes; let the user decide.
