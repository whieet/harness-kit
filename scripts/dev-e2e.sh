#!/usr/bin/env bash
# dev-e2e.sh — one-command live e2e: drives a REAL headless Claude Code instance
# with the local plugin loaded (--plugin-dir), replays every harness discipline
# as a scenario, then has a 3-judge AI panel audit the evidence against
# tests/e2e_workflow_rubric.md. All judgement logic lives in dev_e2e_check.py.
#
# Usage:  bash scripts/dev-e2e.sh [probe|full|audit-only|scenario <SC-N>]
# Env:    E2E_OUT_DIR        output dir (default: mktemp; CI sets it for artifacts)
#         E2E_MODEL          model override (default: your Claude Code default model)
#         E2E_MAX_BUDGET     optional --max-budget-usd escape hatch (default: none)
#         E2E_ISOLATE_HOME=1 scratch $HOME (CI; requires ANTHROPIC_API_KEY auth)
#
# Locally this reuses your logged-in Claude Code state (subscription auth).
# NOTE: never pass --bare here — it would skip hooks, defeating the point.
set -u

KIT="$(cd "$(dirname "$0")/.." && pwd)"

# Locate a Python 3 interpreter portably (same probe order as scripts/lib/pyfind.sh —
# Git for Windows often ships only `python` or `py -3`). Honors HARNESS_PY override.
PY="${HARNESS_PY:-}"
if [ -z "$PY" ] || ! command -v "${PY%% *}" >/dev/null 2>&1; then
  PY=""
  for c in python3 python "py -3"; do
    if command -v "${c%% *}" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "dev-e2e: Python 3 not found on PATH (need python3, python, or 'py -3')"; exit 2; }

# $PY is intentionally unquoted below so "py -3" word-splits into two argv entries.
CHECK() { $PY "$KIT/scripts/dev_e2e_check.py" "$@"; }
MODE="${1:-full}"
OUT="${E2E_OUT_DIR:-$(mktemp -d)}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"  # absolute: run_claude redirects from inside project dirs
FAILURES=""

command -v claude >/dev/null 2>&1 || { echo "dev-e2e: claude CLI not found on PATH"; exit 2; }
command -v git >/dev/null 2>&1 || { echo "dev-e2e: git not found"; exit 2; }

if [ "${E2E_ISOLATE_HOME:-0}" = "1" ]; then
  [ -n "${ANTHROPIC_API_KEY:-}" ] || {
    echo "dev-e2e: E2E_ISOLATE_HOME=1 wipes login state — ANTHROPIC_API_KEY is required"; exit 2; }
  export HOME="$OUT/home"
  mkdir -p "$HOME"
fi

CLAUDE_ARGS=(--plugin-dir "$KIT" --output-format stream-json --verbose \
  --include-hook-events --dangerously-skip-permissions)
[ -n "${E2E_MODEL:-}" ] && CLAUDE_ARGS+=(--model "$E2E_MODEL")
[ -n "${E2E_MAX_BUDGET:-}" ] && CLAUDE_ARGS+=(--max-budget-usd "$E2E_MAX_BUDGET")

note() { printf '\n== %s ==\n' "$*"; }
RATE_LIMITED=0
INCONCLUSIVE=""
fail() { FAILURES="$FAILURES $1"; }

check_or_record() { # <name> <check-cmd...> — maps checker exit codes to suite state
  local name="$1"; shift
  "$@"
  case $? in
    0) ;;
    3) INCONCLUSIVE="$INCONCLUSIVE $name"; RATE_LIMITED=1 ;;
    *) fail "$name" ;;
  esac
}

new_proj() {
  mkdir -p "$1"
  git -C "$1" init -q -b main
  git -C "$1" config user.email e2e@harness-kit.test
  git -C "$1" config user.name harness-e2e
}

pre_init() { # <proj> <type> — deterministic scaffold, no model involved
  (cd "$1" && HARNESS_KIT_ROOT="$KIT" CLAUDE_PROJECT_DIR="$1" \
    $PY "$KIT/scripts/harness_main.py" harness-init "$2" --no-claude-md >/dev/null)
}

tighten() { # <proj> <codeGlob> <loopThreshold> <gatesJson>
  $PY - "$1" "$2" "$3" "$4" <<'PY'
import json, sys
path = sys.argv[1] + "/.harness/config.json"
cfg = json.load(open(path))
cfg.setdefault("plan", {})["codeGlob"] = sys.argv[2]
cfg.setdefault("loopDetection", {})["threshold"] = int(sys.argv[3])
cfg["gates"] = json.loads(sys.argv[4])
json.dump(cfg, open(path, "w"), indent=2)
PY
}

run_claude() { # <proj> <out.jsonl> <prompt>
  local rc=0
  (cd "$1" && claude -p "$3" "${CLAUDE_ARGS[@]}" >"$2" 2>"$2.err") || rc=$?
  echo "$rc" > "$2.rc"
  [ "$rc" != "0" ] && echo "    claude exited $rc (stderr/stream kept beside $2)"
  if [ -s "$2.err" ]; then sed 's/^/    stderr: /' "$2.err" | head -3; fi
}

GATES_SOFT_BUDGET='[{"name":"claude-md-budget","command":"test ! -f CLAUDE.md || test \"$(wc -l < CLAUDE.md)\" -le 200 || { echo \"CLAUDE.md exceeds 200 lines — move detail into docs/\"; exit 1; }","blocking":false}]'
GATES_FIXED_MARKER='[{"name":"fixed-marker","command":"test -f FIXED || { echo \"To pass this gate: create an empty file named FIXED at the repo root (touch FIXED), then finish again.\"; exit 1; }","blocking":true}]'

run_probe() {
  note "probe — do plugin hooks fire headlessly?"
  local D="$OUT/probe"; new_proj "$D/proj"; pre_init "$D/proj" custom
  run_claude "$D/proj" "$OUT/probe.jsonl" "Reply with exactly OK"
  check_or_record probe CHECK probe --out "$OUT" --proj "$D/proj"
}

run_sc1() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-1 init via real slash command"
  local D="$OUT/sc-1"; new_proj "$D/proj"
  printf '{ "name": "e2e-app", "version": "0.0.0" }\n' > "$D/proj/package.json"
  run_claude "$D/proj" "$D/run.jsonl" "/harness-kit:init web"
  check_or_record SC-1 CHECK scenario SC-1 --out "$D" --proj "$D/proj"
}

run_sc2() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-2 plan-gate + Definition-of-Done loop"
  local D="$OUT/sc-2"; new_proj "$D/proj"; pre_init "$D/proj" custom
  tighten "$D/proj" '\.py$' 5 "$GATES_SOFT_BUDGET"
  run_claude "$D/proj" "$D/run.jsonl" "Create hello.py with a function greet(name) that returns 'Hello, <name>'. The harness scaffolds a plan file on your first edit — fill in its '(Fill in:)' sections, and once the work is genuinely done, check off every '- [ ]' item in its Definition of Done, then finish."
  check_or_record SC-2 CHECK scenario SC-2 --out "$D" --proj "$D/proj"
}

run_sc3() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-3 strict Stop gate: block, remediate, pass"
  local D="$OUT/sc-3"; new_proj "$D/proj"; pre_init "$D/proj" custom
  tighten "$D/proj" '' 5 "$GATES_FIXED_MARKER"
  run_claude "$D/proj" "$D/run.jsonl" "Create done.txt containing the single word: done. Then finish."
  check_or_record SC-3 CHECK scenario SC-3 --out "$D" --proj "$D/proj"
}

run_sc4() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-4 loop detection under real repeated edits"
  local D="$OUT/sc-4"; new_proj "$D/proj"; pre_init "$D/proj" custom
  tighten "$D/proj" '' 3 '[]'
  printf 'count = 0\n' > "$D/proj/counter.py"
  git -C "$D/proj" add counter.py
  git -C "$D/proj" commit -q -m seed
  run_claude "$D/proj" "$D/run.jsonl" "counter.py currently contains 'count = 0'. Make 5 separate edits to counter.py, strictly one at a time: each edit increments the number by exactly 1, ending at 'count = 5'. Use a separate Edit tool call per step — do not batch the changes. Then finish."
  check_or_record SC-4 CHECK scenario SC-4 --out "$D" --proj "$D/proj"
}

run_sc5() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-5 evaluator subagent (Generator/Evaluator separation)"
  local D="$OUT/sc-5"; mkdir -p "$D"
  [ -d "$OUT/sc-2/proj" ] || {
    [ "$MODE" = "scenario" ] && { echo "error: SC-5 needs a prior SC-2 run in this E2E_OUT_DIR"; exit 2; }
    echo "  skip: needs SC-2 project"; return; }
  run_claude "$OUT/sc-2/proj" "$D/run.jsonl" "/harness-kit:evaluate"
  check_or_record SC-5 CHECK scenario SC-5 --out "$D" --proj "$OUT/sc-2/proj"
}

run_sc6() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip: rate-limited earlier — not burning more quota"; return; }
  note "SC-6 cross-session continuity"
  local D="$OUT/sc-6"; mkdir -p "$D"
  [ -d "$OUT/sc-2/proj" ] || {
    [ "$MODE" = "scenario" ] && { echo "error: SC-6 needs a prior SC-2 run in this E2E_OUT_DIR"; exit 2; }
    echo "  skip: needs SC-2 project"; return; }
  local before
  before=$(grep -c '"event":"session_start"' "$OUT/sc-2/proj/.harness/state/trace.jsonl" 2>/dev/null || echo 0)
  run_claude "$OUT/sc-2/proj" "$D/run.jsonl" "In one short paragraph: what was being worked on in the previous session in this repo, and what is its current status? Name the plan file."
  check_or_record SC-6 CHECK scenario SC-6 --out "$D" --proj "$OUT/sc-2/proj" --min-starts $((before + 1))
}

run_audit() {
  [ "$RATE_LIMITED" = "1" ] && { echo "  skip audit: rate-limited — judges would throttle too"; return; }
  note "AI audit — 3 independent judges score the rubric on the evidence"
  local PYTEST_SUMMARY
  PYTEST_SUMMARY="$(cd "$KIT" && $PY -m pytest tests -q -m 'not live' 2>&1 | tail -1)"
  echo "  deterministic suite: $PYTEST_SUMMARY"
  CHECK merge --out "$OUT" --pytest "$PYTEST_SUMMARY"
  CHECK audit-prompt --out "$OUT" --rubric "$KIT/tests/e2e_workflow_rubric.md" > "$OUT/audit-prompt.txt"
  local i
  for i in 1 2 3; do
    (cd "$OUT" && claude -p "$(cat "$OUT/audit-prompt.txt")" --output-format json \
      --dangerously-skip-permissions ${E2E_MODEL:+--model "$E2E_MODEL"} \
      > "$OUT/judge-$i.json" 2>/dev/null) &
  done
  wait
  CHECK audit-merge --out "$OUT" || fail audit
}

case "$MODE" in
  probe) run_probe ;;
  scenario)
    case "${2:?usage: dev-e2e.sh scenario SC-N}" in
      SC-1) run_sc1 ;; SC-2) run_sc2 ;; SC-3) run_sc3 ;;
      SC-4) run_sc4 ;; SC-5) run_sc5 ;; SC-6) run_sc6 ;;
      *) echo "unknown scenario: $2"; exit 2 ;;
    esac ;;
  audit-only) run_audit ;;
  full)
    run_probe
    if [ -n "$FAILURES" ]; then
      echo; echo "probe hard-failed — the plugin is not working headlessly; aborting the suite."
    else
      run_sc1; run_sc2; run_sc3; run_sc4; run_sc5; run_sc6; run_audit
    fi ;;
  *) echo "usage: dev-e2e.sh [probe|full|audit-only|scenario SC-N]"; exit 2 ;;
esac

note "summary"
echo "  artifacts: $OUT"
if [ -n "$FAILURES" ]; then
  echo "  ❌ failed:$FAILURES"
  [ -n "$INCONCLUSIVE" ] && echo "  ⏳ inconclusive (rate-limited):$INCONCLUSIVE"
  exit 1
fi
if [ -n "$INCONCLUSIVE" ]; then
  CHECK merge --out "$OUT" >/dev/null 2>&1 || true   # keep evidence.json for artifacts
  echo "  ⏳ inconclusive (upstream rate limit):$INCONCLUSIVE — re-run after the quota window resets"
  exit 3
fi
echo "  ✅ all hard assertions passed"
