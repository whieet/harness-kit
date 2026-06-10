# Testing & Evaluation

**English** · [简体中文](./testing.md)

> The Simplified Chinese [testing.md](./testing.md) is the authoritative version; this page mirrors it.

Verifying harness-kit does not rely on "make a directory → open Claude → install the plugin → poke around". Four pyramid layers, one command each:

| Layer | What | Calls Claude? | When |
| --- | --- | --- | --- |
| **L1 unit/parity** | smoke, parity (frozen bash oracle), d-suites (determinism / robustness / parity fuzz / concurrency) | No | push to main / PRs (CI: 3 OS × 2 Python matrix) |
| **L2 structure + session replay** | `test_structure.py` (cross-file invariants) + `test_e2e_session.py` (S1–S7: replays hook sequences in real-session order, asserting trace/plan/snapshot state evolution) | No | push to main / PRs |
| **L3 live scenario suite** | `scripts/dev-e2e.sh`: a real headless Claude (plugin loaded via `--plugin-dir`) runs SC-1..SC-6 — one live scenario per core discipline | **Yes** | locally on demand; CI: push to main + daily + dispatch |
| **L4 conformance audit + blueprint benchmark** | 3 independent AI judges score [`tests/e2e_workflow_rubric.md`](../tests/e2e_workflow_rubric.md) row-by-row with majority vote; [`docs/benchmark.md`](./benchmark.md) compares against the man-in-the-mirror blueprint | **Yes** | with L3 full |

## Prerequisites

| Layer | Needs |
| --- | --- |
| L1 + L2 | Python 3.9+, pytest (`python3 -m pip install pytest`), git. Optionally `jsonschema` (enables 1 extra schema-validation test; auto-skips when absent) |
| manifest validation | the Claude Code CLI (`claude` on PATH); **no model calls, no login needed** |
| L3 + L4 | the `claude` CLI + auth: locally your logged-in Claude Code (subscription) is enough; CI uses `ANTHROPIC_API_KEY` |

Run every command from the **repo root** (pytest relies on the `tests` package imports).

## Platform support

| What | macOS / Linux | Windows |
| --- | --- | --- |
| L1 smoke + d1/d3/d9 | ✅ | ✅ (CI matrix includes `windows-latest`, via Git Bash) |
| L1 parity family (parity / parity_extra / d7) | ✅ (needs the old bash impl in git history; auto-skips on shallow clones) | ⛔ **auto-skipped** — the oracle needs a Unix toolchain; `skipif` skips cleanly, no errors |
| L2 structure + session replay | ✅ | ✅ (included in the CI Windows job step) |
| manifest validation | ✅ | ✅ |
| L3/L4 live (dev-e2e.sh) | ✅ (verified by real runs) | ⚠️ should work: run inside **Git Bash** (the same way the plugin itself supports Windows); the interpreter is probed as `python3 → python → py -3` (override with `HARNESS_PY`); **not yet live-verified on Windows** |

CI split: the Windows job runs smoke + structure + replay; the ubuntu job runs the full deterministic suite (incl. d-suites) and the live e2e; the macOS job covers parity. Locally on Windows, a manual `python -m pytest tests` runs everything (parity auto-skips).

## How to run

### L1 + L2 — deterministic suite (~1 minute, no model calls)

```bash
python3 -m pytest tests -v
```

Expected tail: `348 passed, 1 skipped, 2 deselected` — the skip is the optional jsonschema
test, the deselected pair is the live layer (never fires by default). A failure means code or
structure drifted; read the assertion.

Only the new layers: `python3 -m pytest tests/test_structure.py tests/test_e2e_session.py -v`

### Strict manifest validation (seconds, no model calls)

```bash
claude plugin validate . --strict
```

Expected: `✔ Validation passed`.

### L3 — live scenario suite (a real Claude)

```bash
bash scripts/dev-e2e.sh probe   # minimal live run (~1-2 min, one tiny session)
bash scripts/dev-e2e.sh full    # all 6 scenarios + 3-judge audit (~15-25 min)
```

- **Run `probe` first**: it gates the core assumption (plugin hooks fire headlessly) and doubles as a cheap check that your quota window is open.
- `full` runs probe → SC-1…SC-6 → audit in order; a probe hard-failure aborts the suite (if the plugin isn't working headlessly, nothing after it is meaningful).
- One measured `full` run costs ≈ $3 at API pricing (subscription login draws from your usage quota instead — no bill).
- The output dir defaults to `mktemp`; the final `artifacts:` line prints the path. Pin it with `E2E_OUT_DIR=/path bash scripts/dev-e2e.sh full`.

Single-scenario debugging and re-audit:

```bash
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh scenario SC-3   # one scenario
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh scenario SC-5   # needs an SC-2 run in the same dir, else exits 2
E2E_OUT_DIR=/tmp/e2e bash scripts/dev-e2e.sh audit-only      # reuse existing evidence, re-run only the 3 judges
```

Environment variables: `E2E_MODEL` (model override; defaults to your Claude Code default),
`E2E_MAX_BUDGET` (runaway insurance, unset by default), `E2E_ISOLATE_HOME=1` (scratch HOME, requires
`ANTHROPIC_API_KEY`; for CI).

Also reachable via pytest (triple-gated; `pytest tests` never fires it):

```bash
HARNESS_LIVE_E2E=1 python3 -m pytest tests/test_live_e2e.py -v -s
```

### Reading the output

```
  [ok]   SC-3:gate_remediation_done      ← hard assertion (filesystem side effect): a failure = harness problem
  [ok] ~ SC-3:stop_hook_exit_2_seen      ← soft assertion (with ~): failures only warn, never fail the suite
```

**Exit codes**: `0` all hard assertions passed; `1` a hard assertion failed; `2` usage/environment
error; `3` **inconclusive** — an upstream rate limit (429 / subscription 5h quota window exhausted)
aborted the session; evidence is kept but not judged, remaining scenarios are skipped to avoid
burning throttled quota; just re-run after the window resets. Note `… | tee log` swallows the exit
code — use `set -o pipefail` to capture it.

### Artifact layout ($OUT)

```
probe.jsonl(.err/.rc)      raw stream-json + stderr + claude exit code
evidence-probe.json        probe's hard/soft assertion results
sc-1/ … sc-6/
  proj/                    the scenario's temp project (.harness/state/trace.jsonl backs the hard assertions)
  run.jsonl(.err/.rc)      that scenario's raw session stream
  evidence-SC-N.json       that scenario's assertion results
evidence.json              merged evidence (+ pytest summary + total cost) — the audit's only input
audit-prompt.txt           the full judge prompt (rubric + evidence)
judge-{1,2,3}.json         the three judges' raw outputs
audit.json                 majority-vote synthesis (rows / failing / disputed)
```

To debug a failed scenario: check which hard assertion failed in `evidence-SC-N.json`, then
cross-reference `sc-N/proj/.harness/state/trace.jsonl` and `sc-N/run.jsonl` (hook_started /
hook_response events carry each hook's output and exit code).

### Troubleshooting

| Symptom | Fix |
| --- | --- |
| `claude CLI not found` | install Claude Code, or fix PATH |
| exit code 3 / `[INCONCLUSIVE]` | subscription quota window exhausted — re-run later (`probe` first) |
| `E2E_ISOLATE_HOME=1 … requires ANTHROPIC_API_KEY` | isolation wipes login state; set the key, or drop the variable locally to use your login |
| SC-5/SC-6 say `needs a prior SC-2 run` | in scenario mode, run `scenario SC-2` in the same `E2E_OUT_DIR` first (or just `full`) |
| judge output unparseable (warn) | one bad judge falls back to the remaining majority; if all fail the audit skips without failing the suite — retry with `audit-only` |

## CI setup

The workflows are in place; once pushed to GitHub:

- **`.github/workflows/test.yml`** (L1+L2): runs on push to main / PRs, 3 OS × Python 3.9/3.12, zero config.
- **`.github/workflows/e2e.yml`**: the `plugin-validate` job always runs (free, no key); the `live-e2e`
  job runs on push to main, daily 03:00 UTC cron, and manual dispatch, and needs `ANTHROPIC_API_KEY`
  under **Settings → Secrets and variables → Actions** — it skips cleanly when the secret is absent.
  Rate-limit aborts surface as a warning, not a red build. Run artifacts (evidence / audit /
  per-scenario run.jsonl) are uploaded for download from the Actions page.

## L3 scenario ↔ discipline map

| Scenario | Discipline verified | Hard assertions (filesystem side effects) |
| --- | --- | --- |
| probe | plugin loads + hooks fire headlessly | `session_start` in trace.jsonl; system/init lists the plugin, no errors |
| SC-1 | real `/harness-kit:init` slash-command path | config / CLAUDE.md / pre-commit scaffolded |
| SC-2 | plan gate + Definition-of-Done loop | `auto-*.md` plan on disk; hello.py exists; session_start/end traced |
| SC-3 | strict Stop gate: block → remediate per stderr → pass | `FIXED` created; trace `session_end` failed then passed |
| SC-4 | loop detection under real repeated edits | `loop-*.json` count ≥ threshold |
| SC-5 | Generator/Evaluator separation (evaluator subagent) | run completes; VERDICT / evaluator trace event (soft) |
| SC-6 | cross-session continuity (SessionStart handoff) | a NEW `session_start` traced (baseline-counted); answer cites last plan (soft) |

**Assertion tiers**: hard assertions prefer filesystem side effects (trace.jsonl, plan files, loop counters) — independent of model cooperation; the only stream-read hard checks (plugin load, run completion) come from the stable `system/init` and `result` events. Hook lifecycle events that depend on the newer `--include-hook-events` flag are always soft (warn, never fail).

## Cost & isolation

- The design premise is **verification quality over token cost**: your default (strong) model, no budget cap. `E2E_MODEL` overrides the model; `E2E_MAX_BUDGET` is a runaway-protection escape hatch (unset by default).
- Locally the script reuses your logged-in Claude Code (subscription auth) and does not isolate `$HOME`.
- In CI, set `E2E_ISOLATE_HOME=1` + the `ANTHROPIC_API_KEY` secret: a scratch HOME fully isolates global config. The live job skips cleanly when the secret is absent.

## How the L4 audit works

`dev-e2e.sh full` merges every scenario's hard/soft assertion results into `evidence.json`
(plus the deterministic suite's pytest summary), then dispatches 3 independent Claude judges
in parallel: they score the rubric row-by-row (`pass / partial / fail / n-a`) strictly from the
evidence; verdicts are combined by a majority **of judges** (split rows are marked `disputed`),
and any decidable row with a majority `fail` fails the pipeline.
