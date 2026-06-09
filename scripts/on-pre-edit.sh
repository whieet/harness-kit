#!/usr/bin/env bash
# on-pre-edit.sh — PreToolUse(Edit|Write|MultiEdit): plan-gate.
# Ported from scripts-tooling/plan-gate.sh, de-coupled from Godot.
# When the edited file matches config.plan.codeGlob and NO active plan covers it,
# auto-scaffold a plan and inject context. Non-blocking: does NOT override the
# user's permission flow (no permissionDecision) — it only scaffolds + informs.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0
harness_cap_enabled planGate || exit 0   # respect config.enabledCapabilities

CODE_GLOB=$(harness_cfg_get plan.codeGlob "")
[ -z "$CODE_GLOB" ] && exit 0   # plan-gate disabled when no codeGlob configured

FILE_PATH=$(printf '%s' "$INPUT" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("tool_input",{}).get("file_path","") or "")
except Exception: print("")' 2>/dev/null || true)
[ -z "$FILE_PATH" ] && exit 0

# Only gate files matching the configured code glob (a regex on the path).
if ! printf '%s' "$FILE_PATH" | grep -qE "$CODE_GLOB"; then
  exit 0
fi

# Realpath-based relpath: cwd from the hook payload and the resolved project root
# may differ by a symlink (e.g. macOS /var -> /private/var), which would break a
# naive prefix strip and leave REL_PATH absolute.
REL_PATH=$(FP="$FILE_PATH" PR="$HARNESS_PROJECT_DIR" python3 -c 'import os
print(os.path.relpath(os.path.realpath(os.environ["FP"]), os.path.realpath(os.environ["PR"])))' 2>/dev/null || echo "$FILE_PATH")
PLAN_DIR=$(harness_cfg_get plan.dir "docs/exec-plans")
ACTIVE_DIR="$PLAN_DIR/active"

# Does any active plan already mention this file?
ACTIVE_PLANS=$(find "$ACTIVE_DIR" -maxdepth 1 -name '*.md' -type f 2>/dev/null | grep -v '.gitkeep' || true)
if [ -n "$ACTIVE_PLANS" ]; then
  while IFS= read -r plan; do
    [ -z "$plan" ] && continue
    if grep -qF "$REL_PATH" "$plan" 2>/dev/null; then
      exit 0   # covered
    fi
  done <<< "$ACTIVE_PLANS"
fi

# --- no covering plan: scaffold one ---
STATUS_FIELD=$(harness_cfg_get plan.statusField "status")
TEMPLATE=$(harness_cfg_get plan.template "")
[ -z "$TEMPLATE" ] && TEMPLATE="$SD/../templates/plan-template.md"
[ -f "$TEMPLATE" ] || exit 0   # no template available; do nothing rather than guess

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H%M%S)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
SLUG=$(printf '%s' "$REL_PATH" | python3 -c 'import sys,re
s=sys.stdin.read().strip()
s=re.sub(r"\.[^.]+$","",s)
s=re.sub(r"[^a-z0-9_/-]","-",s.lower())
parts=[p for p in s.split("/") if p]
print(("-".join(parts[-3:]))[:60] or "session")' 2>/dev/null || echo session)
TITLE=$(printf '%s' "$REL_PATH" | sed -E 's/\.[^.]+$//; s#/# / #g')

mkdir -p "$ACTIVE_DIR"
PLAN_FILE="$ACTIVE_DIR/auto-${DATE}-${TIME}-${SLUG}.md"

# Substitute placeholders in the template.
TITLE="$TITLE" STATUS_FIELD="$STATUS_FIELD" DATE="$DATE" TIMESTAMP="$TIMESTAMP" \
REL_PATH="$REL_PATH" SOURCE="plan-gate (auto-created on first edit of \`$REL_PATH\` with no covering plan)" \
python3 - "$TEMPLATE" "$PLAN_FILE" <<'PYEOF'
import os, sys
tpl = open(sys.argv[1]).read()
for k in ("TITLE", "STATUS_FIELD", "DATE", "TIMESTAMP", "REL_PATH", "SOURCE"):
    tpl = tpl.replace("{{%s}}" % k, os.environ.get(k, ""))
open(sys.argv[2], "w").write(tpl)
PYEOF

RECENT=$(git log --oneline -3 2>/dev/null | sed 's/^/  /' || echo "  (none)")
CTX="Auto-created plan: $PLAN_FILE
No active plan covered \`$REL_PATH\`. A scaffold plan was created — fill in its
Background, Goals, and Steps, and check off the Definition of Done as you work.
The Stop-hook pre-completion gate will verify the DoD before you finish.

Recent commits:
$RECENT"

CTX_FILE=$(mktemp)
printf '%s' "$CTX" > "$CTX_FILE"
python3 - "$CTX_FILE" <<'PYEOF'
import json, sys
ctx = open(sys.argv[1]).read()
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ctx}}, ensure_ascii=False))
PYEOF
rm -f "$CTX_FILE"
exit 0
