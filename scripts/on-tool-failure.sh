#!/usr/bin/env bash
# on-tool-failure.sh — PostToolUseFailure, async, lightweight.
# Records a tool_fail record so harness-trace-analyze can report failure rate and
# repeated-failure patterns (e.g. a gate failing every turn = stack instability).
# Gated by config.enabledCapabilities.toolTrace. (exit_code may be absent in the
# payload — recorded best-effort.)
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
ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
rec = {"ts": ts, "event": "tool_fail", "tool": tool}
for k in ("exit_code", "error_message"):
    if k in d:
        rec[k] = d[k]
try:
    with open(os.environ["HK_TRACE"], "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
except Exception:
    pass
' 2>/dev/null || true
exit 0
