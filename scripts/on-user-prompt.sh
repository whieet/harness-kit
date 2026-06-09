#!/usr/bin/env bash
# on-user-prompt.sh — UserPromptSubmit: re-inject the harness state ONCE after a
# compaction. PreCompact wrote a snapshot + a dirty marker; if the marker is
# present, emit a terse "Harness state before compaction" block as additionalContext
# (a documented UserPromptSubmit capability) and clear the marker, so it injects
# exactly once. Gated by config.enabledCapabilities.contextSnapshot.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
harness_cap_enabled contextSnapshot || exit 0
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

STATE="$(harness_state_dir)"
[ -f "$STATE/pre-compact.dirty" ] || exit 0   # nothing to recover

CTX=$(STATE="$STATE" python3 <<'PYEOF'
import json, os
state = os.environ["STATE"]
snap_path = os.path.join(state, "pre-compact-snapshot.json")
if not os.path.exists(snap_path):
    raise SystemExit(0)
try:
    s = json.load(open(snap_path))
except Exception:
    raise SystemExit(0)
parts = ["Harness state carried across compaction:"]
for p in s.get("plans", []):
    parts.append("  - active plan %s: %d/%d DoD checked" % (p["name"], p.get("checked", 0), p.get("total", 0)))
if not s.get("plans"):
    parts.append("  - no active plans")
if s.get("lastGateResult"):
    parts.append("  - last completion gate: %s" % s["lastGateResult"])
if s.get("recentFailedGates"):
    parts.append("  - recently failing gates: %s" % ", ".join(s["recentFailedGates"]))
parts.append("Finish the unchecked DoD items and pass the gates before declaring done.")
print("\n".join(parts))
PYEOF
)

rm -f "$STATE/pre-compact.dirty"
[ -z "$CTX" ] && exit 0

CTX_FILE=$(mktemp)
printf '%s' "$CTX" > "$CTX_FILE"
python3 - "$CTX_FILE" <<'PYEOF'
import json, sys
ctx = open(sys.argv[1]).read()
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}, ensure_ascii=False))
PYEOF
rm -f "$CTX_FILE"
exit 0
