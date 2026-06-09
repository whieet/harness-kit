#!/usr/bin/env bash
# on-post-tool.sh — PostToolUse (ALL tools), async, lightweight.
# Records one tool-call record per tool use so harness-trace-analyze can recover
# tool-level signals (repeated-tool loops, edits-before-verify, churn) that the
# session_start/session_end events alone cannot show.
# Gated by config.enabledCapabilities.toolTrace.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
harness_cap_enabled toolTrace || exit 0
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

TRACE="$(harness_state_dir)/trace.jsonl"
printf '%s' "$INPUT" | HK_TRACE="$TRACE" python3 -c '
import json, sys, os, datetime
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
tool = d.get("tool_name", "")
if not tool:
    sys.exit(0)
ti = d.get("tool_input") or {}
fp = ti.get("file_path", "") if isinstance(ti, dict) else ""
ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
rec = {"ts": ts, "event": "tool_call", "tool": tool}
if fp:
    rec["file"] = fp
try:
    with open(os.environ["HK_TRACE"], "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
except Exception:
    pass
' 2>/dev/null || true
exit 0
