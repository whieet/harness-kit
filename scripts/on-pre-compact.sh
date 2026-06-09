#!/usr/bin/env bash
# on-pre-compact.sh — PreCompact: snapshot the harness control-plane to disk so the
# context-management contract (which plan, which unchecked DoD, which failed gate)
# survives compaction. Pairs with on-user-prompt.sh (re-injects once after compaction)
# and on-session-start.sh (surfaces on resume). PostCompact additionalContext is NOT
# supported, so the snapshot + a dirty marker are the supported recovery path.
# Gated by config.enabledCapabilities.contextSnapshot.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
harness_cap_enabled contextSnapshot || exit 0
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

STATE="$(harness_state_dir)"
PLAN_DIR=$(harness_cfg_get plan.dir "docs/exec-plans")

STATE="$STATE" PLAN_DIR="$PLAN_DIR" python3 <<'PYEOF'
import json, os, glob, re, datetime
state = os.environ["STATE"]
active = os.path.join(os.environ["PLAN_DIR"], "active")

unchecked_re = re.compile(r"^- \[ \]")
checked_re = re.compile(r"^- \[[xX]\]")
plans = []
for p in glob.glob(os.path.join(active, "*.md")):
    if os.path.basename(p) == ".gitkeep":
        continue
    try:
        lines = open(p, errors="replace").read().splitlines()
    except Exception:
        continue
    u = sum(1 for l in lines if unchecked_re.search(l))
    c = sum(1 for l in lines if checked_re.search(l))
    if u + c > 0:
        plans.append({"name": os.path.basename(p), "checked": c, "total": u + c})

last_result, recent_fail = None, []
trace = os.path.join(state, "trace.jsonl")
if os.path.exists(trace):
    recs = []
    for line in open(trace, errors="replace"):
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    for r in reversed(recs):
        if r.get("event") == "session_end":
            last_result = r.get("result")
            break
    for r in recs[-60:]:
        if r.get("event") == "gate" and not r.get("ok", True):
            recent_fail.append(r.get("name"))

snap = {
    "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "plans": plans,
    "lastGateResult": last_result,
    "recentFailedGates": list(dict.fromkeys(recent_fail))[-5:],
}
try:
    with open(os.path.join(state, "pre-compact-snapshot.json"), "w") as f:
        json.dump(snap, f, ensure_ascii=False)
    open(os.path.join(state, "pre-compact.dirty"), "w").close()
except Exception:
    pass
PYEOF
exit 0
