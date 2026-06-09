#!/usr/bin/env bash
# on-session-start.sh — SessionStart: inject a session handoff as additionalContext.
# Ported from scripts-tooling/session-start.sh, de-coupled from Godot.
# Composes native git state + active plans + (optional) harness-advisor phase report
# + config-driven key-docs + a generic checklist. stdout JSON is added to Claude context.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

PLAN_DIR=$(harness_cfg_get plan.dir "docs/exec-plans")
ACTIVE_DIR="$PLAN_DIR/active"

GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo unknown)
UNCOMMITTED=$(git diff --name-only 2>/dev/null | wc -l | tr -d ' ')
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')
RECENT=$(git log --oneline -5 2>/dev/null || echo "(no commits)")

ACTIVE_PLANS=$(find "$ACTIVE_DIR" -maxdepth 1 -name '*.md' -type f 2>/dev/null | grep -v '.gitkeep' || true)
ACTIVE_COUNT=$(printf '%s' "$ACTIVE_PLANS" | grep -c . || true)

# Optional phase report (present once P2 ships harness-advisor and config has metrics).
ADVISOR="$SD/../bin/harness-advisor"
ADVISOR_OUT=""
if [ -x "$ADVISOR" ]; then
  ADVISOR_OUT=$(bash "$ADVISOR" 2>/dev/null || true)
fi

KEYDOCS=$(harness_py 'rows=cfg.get("docs",{}).get("keyDocs",[])
print("\n".join("- %s — %s" % (d.get("path",""), d.get("note","")) for d in rows))')

CTX_FILE=$(mktemp)
{
  echo "=== Session Handoff (harness-kit) ==="
  echo ""
  if [ -n "$ADVISOR_OUT" ]; then echo "$ADVISOR_OUT"; echo ""; fi
  echo "Git: branch=$GIT_BRANCH, uncommitted=$UNCOMMITTED, untracked=$UNTRACKED"
  echo "Recent commits:"
  echo "$RECENT"
  echo ""
  echo "Active plans ($ACTIVE_COUNT):"
  if [ "$ACTIVE_COUNT" -gt 0 ]; then
    echo "$ACTIVE_PLANS" | sed 's/^/  /'
  else
    echo "  (none — create one before editing planned code)"
  fi
  if [ -n "$KEYDOCS" ]; then
    echo ""
    echo "Key docs:"
    echo "$KEYDOCS"
  fi
  # Resume context: if a pre-compaction snapshot exists, surface unfinished work.
  SNAP="$(harness_state_dir)/pre-compact-snapshot.json"
  if [ -f "$SNAP" ] && harness_cap_enabled contextSnapshot; then
    RESUME=$(SNAP="$SNAP" python3 -c '
import json, os
try: s = json.load(open(os.environ["SNAP"]))
except Exception: raise SystemExit(0)
ps = s.get("plans", [])
incomplete = [p for p in ps if p.get("checked", 0) < p.get("total", 0)]
if incomplete or s.get("lastGateResult") in ("failed", "advisory_fail"):
    out = ["Resuming — unfinished from before:"]
    for p in incomplete:
        out.append("  - %s: %d/%d DoD" % (p["name"], p.get("checked",0), p.get("total",0)))
    if s.get("recentFailedGates"):
        out.append("  - recently failing gates: %s" % ", ".join(s["recentFailedGates"]))
    print("\n".join(out))
' 2>/dev/null || true)
    if [ -n "$RESUME" ]; then
      echo ""
      echo "$RESUME"
    fi
  fi
  echo ""
  echo "Harness (auto via plugin hooks — you do not run these): SessionStart handoff;"
  echo "PreToolUse plan-gate; PostToolUse loop-detect; Stop pre-completion verify gate."
} > "$CTX_FILE"
# Session start supersedes the mid-session re-inject; clear the dirty marker.
rm -f "$(harness_state_dir)/pre-compact.dirty" 2>/dev/null || true

python3 - "$CTX_FILE" <<'PYEOF'
import json, sys
ctx = open(sys.argv[1]).read()
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}, ensure_ascii=False))
PYEOF
rm -f "$CTX_FILE"

# Trace: session_start (Ralph-Loop signal not in the native transcript)
TRACE="$(harness_state_dir)/trace.jsonl"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"ts\":\"$TS\",\"event\":\"session_start\"}" >> "$TRACE" 2>/dev/null || true
exit 0
