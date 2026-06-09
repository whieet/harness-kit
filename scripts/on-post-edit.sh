#!/usr/bin/env bash
# on-post-edit.sh — PostToolUse(Edit|Write|MultiEdit): per-file loop detection.
# Ported from scripts-tooling/loop-detect.sh. Tracks how many times each file is
# touched in THIS session (keyed by session_id, state in .harness/state/, gitignored).
# When a file crosses the threshold, inject a "reconsider your approach" nudge.
#
# Injection: print to stderr + exit 2. For PostToolUse, exit 2 is NON-BLOCKING and
# feeds stderr to Claude (documented contract) — the tool already ran, this only nudges.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0
harness_cap_enabled loopDetection || exit 0   # respect config.enabledCapabilities

SESSION_ID=$(printf '%s' "$INPUT" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("session_id","default") or "default")
except Exception: print("default")' 2>/dev/null || echo default)

THRESHOLD=$(harness_cfg_get loopDetection.threshold "${CLAUDE_PLUGIN_OPTION_LOOP_THRESHOLD:-5}")

DIFF_STAT=$(git diff --numstat 2>/dev/null || true)
STAGED_STAT=$(git diff --staged --numstat 2>/dev/null || true)
{ [ -z "$DIFF_STAT" ] && [ -z "$STAGED_STAT" ]; } && exit 0

STATE_FILE="$(harness_state_dir)/loop-${SESSION_ID}.json"
IGNORE=$(harness_py 'print("\n".join(cfg.get("loopDetection",{}).get("ignoreGlobs",[])))')

# NOTE: the diff is passed via env var, NOT stdin — `python3 - <<HEREDOC` already
# uses stdin for the program, so a piped diff would be silently discarded. (The
# upstream loop-detect.sh had exactly this bug and never actually fired.)
WARN=$(HARNESS_DIFF="$(printf '%s\n%s' "$DIFF_STAT" "$STAGED_STAT")" \
  python3 - "$STATE_FILE" "$THRESHOLD" "$IGNORE" <<'PYEOF'
import json, sys, os, fnmatch
state_file, threshold = sys.argv[1], int(sys.argv[2])
ignore = [g for g in sys.argv[3].split('\n') if g] if sys.argv[3] else []
state = {}
if os.path.exists(state_file):
    try:
        state = json.load(open(state_file))
    except Exception:
        state = {}
touched = set()
for line in os.environ.get("HARNESS_DIFF", "").strip().split('\n'):
    parts = line.split('\t')
    if len(parts) >= 3:
        fp = parts[2]
        if any(fnmatch.fnmatch(fp, g) for g in ignore):
            continue
        touched.add(fp)
warnings = []
for fp in touched:
    c = state.get(fp, 0) + 1
    state[fp] = c
    if c >= threshold:
        warnings.append((fp, c))
os.makedirs(os.path.dirname(state_file), exist_ok=True)
json.dump(state, open(state_file, 'w'), ensure_ascii=False)
out = []
for fp, c in warnings:
    out.append(f"  ⚠️  Loop detection: {fp} edited {c}× this session.")
    out.append("     Consider: (1) re-read the task spec to confirm the goal; (2) try a different approach instead of micro-tweaking this file.")
print('\n'.join(out))
PYEOF
)

if [ -n "$WARN" ]; then
  printf '%s\n' "$WARN" >&2
  exit 2   # PostToolUse: non-blocking, stderr injected to Claude
fi
exit 0
