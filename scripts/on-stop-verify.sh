#!/usr/bin/env bash
# on-stop-verify.sh — Stop: pre-completion verification gate (the "Ralph Loop").
# Ported from scripts-tooling/verify-completion.sh. Runs the config-driven verify
# orchestrator + uncommitted-changes check + active-plan DoD self-check + (optional)
# evaluator guidance. In verificationMode=strict, a failure exits 2 to BLOCK the
# agent from ending its turn (stderr is injected so it knows what to fix).
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

# Route all output to stderr — on exit 2 (block), Claude Code injects stderr to the agent.
exec >&2

MODE=$(harness_cfg_get verificationMode "${CLAUDE_PLUGIN_OPTION_VERIFICATION_MODE:-strict}")
PLAN_DIR=$(harness_cfg_get plan.dir "docs/exec-plans")
BIN="$SD/../bin"
FAIL=0

echo "=== harness-kit: pre-completion gate ==="

# [1] verification orchestrator
echo "[1/3] harness-verify"
VOUT=$(bash "$BIN/harness-verify" 2>&1); VRC=$?
printf '%s\n' "$VOUT" | sed 's/^/  /'
[ "$VRC" -ne 0 ] && FAIL=1

# [2] uncommitted changes (advisory)
echo "[2/3] uncommitted changes"
CH=$(git diff --name-only 2>/dev/null | head -20)
ST=$(git diff --staged --name-only 2>/dev/null | head -20)
UN=$(git ls-files --others --exclude-standard 2>/dev/null | { grep -v '\.uid$' || true; } | head -10)
if [ -z "$CH$ST$UN" ]; then
  echo "  ✓ working tree clean"
else
  echo "  ⚠️  uncommitted work present — commit if this is a real milestone"
fi

# [3] active-plan DoD self-check
echo "[3/3] active-plan DoD"
ACTIVE=$(find "$PLAN_DIR/active" -maxdepth 1 -name '*.md' -type f 2>/dev/null | grep -v '.gitkeep' || true)
if [ -n "$ACTIVE" ]; then
  while IFS= read -r plan; do
    [ -z "$plan" ] && continue
    UNCH=$(grep -cE '^- \[ \]' "$plan" 2>/dev/null | tr -d '[:space:]' || echo 0); UNCH=${UNCH:-0}
    CHK=$(grep -cE '^- \[[xX]\]' "$plan" 2>/dev/null | tr -d '[:space:]' || echo 0); CHK=${CHK:-0}
    TOT=$((UNCH + CHK))
    if [ "$TOT" -gt 0 ] && [ "$UNCH" -gt 0 ]; then
      if [ "$CHK" -gt 0 ]; then
        echo "  ❌ $(basename "$plan"): $CHK/$TOT done, $UNCH unfinished — blocking"
        FAIL=1
      else
        echo "  ⚠️  $(basename "$plan"): $UNCH items, none checked yet (maybe just started)"
      fi
    elif [ "$TOT" -gt 0 ]; then
      echo "  ✓ $(basename "$plan"): all $TOT done"
    fi
  done <<< "$ACTIVE"
else
  echo "  (no active plans)"
fi

# [optional] evaluator guidance (Generator/Evaluator separation). A bash hook can't
# compute a subjective score, so it surfaces the rubric + recipe and recommends
# running /harness-kit:evaluate (which dispatches the evaluator subagent). It does
# not auto-block on score. Gated by config.enabledCapabilities.evaluator.
# Effort-aware: at low/medium effort with routing ON, the evaluator is part of the
# 'full' verification phase and is deferred (kept light) — matching the Sandwich.
EVAL_EFFORT="${CLAUDE_EFFORT:-}"
EVAL_ROUTING="$(harness_cfg_get effortRouting.enabled false)"
if harness_cap_enabled evaluator; then
  CODE_GLOB=$(harness_cfg_get plan.codeGlob "")
  CHANGED=$(printf '%s\n%s' "$CH" "$ST")
  if [ -n "$CODE_GLOB" ] && printf '%s' "$CHANGED" | grep -qE "$CODE_GLOB"; then
    if [ "$EVAL_ROUTING" = "true" ] && { [ "$EVAL_EFFORT" = "low" ] || [ "$EVAL_EFFORT" = "medium" ]; }; then
      echo ""
      echo "[evaluator] code changed — deferred at effort=$EVAL_EFFORT (run /harness-kit:evaluate at high effort before final completion)."
    else
      echo ""
      echo "[evaluator] code changed — run /harness-kit:evaluate (dispatches the evaluator subagent, fresh context) to score this change."
      RUBRIC=$(harness_cfg_get evaluator.rubricPath "")
      [ -n "$RUBRIC" ] && echo "  rubric: $RUBRIC"
      echo "  verification recipe (dimension → check):"
      harness_py 'r = cfg.get("verificationRecipe", {})
for k, v in r.items():
    print("    - %s: %s" % (k, v))'
      echo "  any dimension scoring <3 = FAIL → revise before declaring done."
    fi
  fi
fi

# trace + verdict
TRACE="$(harness_state_dir)/trace.jsonl"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
if [ "$FAIL" -ne 0 ] && [ "$MODE" = "strict" ]; then
  echo "{\"ts\":\"$TS\",\"event\":\"session_end\",\"result\":\"failed\"}" >> "$TRACE" 2>/dev/null || true
  echo "=== ❌ pre-completion gate failed — fix the above before finishing (verificationMode=strict) ==="
  exit 2
fi
RESULT="passed"; [ "$FAIL" -ne 0 ] && RESULT="advisory_fail"
echo "{\"ts\":\"$TS\",\"event\":\"session_end\",\"result\":\"$RESULT\"}" >> "$TRACE" 2>/dev/null || true
if [ "$FAIL" -ne 0 ]; then
  echo "=== ⚠️  pre-completion gate found issues (advisory mode — not blocking) ==="
else
  echo "=== ✅ pre-completion gate passed ==="
fi
exit 0
