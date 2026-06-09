#!/usr/bin/env bash
# on-plan-approved.sh — PostToolUse(ExitPlanMode): persist the approved plan.
# Ported from scripts-tooling/on-plan-approved.sh, field labels config-driven,
# English template. Claude Code presents/approves plans natively but does not
# persist them to a project file — this hook captures tool_input.plan into the
# configured plan directory with metadata + a DoD stub.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/enabled.sh
source "$SD/lib/enabled.sh"     # sources config; exits 0 if project not harness-initialized
cd "$HARNESS_PROJECT_DIR" 2>/dev/null || exit 0

PLAN_DIR=$(harness_cfg_get plan.dir "docs/exec-plans")
STATUS_FIELD=$(harness_cfg_get plan.statusField "status")
ACTIVE_DIR="$PLAN_DIR/active"
mkdir -p "$ACTIVE_DIR"
DATE=$(date +%Y-%m-%d)

# Everything is handled in python (plan text is arbitrary markdown — no shell quoting).
# INPUT is passed via env, NOT stdin: `python3 - <<HEREDOC` already takes its program
# from stdin, so a piped payload would be silently discarded.
HK_INPUT="$INPUT" ACTIVE_DIR="$ACTIVE_DIR" STATUS_FIELD="$STATUS_FIELD" DATE="$DATE" python3 - <<'PYEOF'
import json, sys, os, re
try:
    data = json.loads(os.environ.get("HK_INPUT", "") or "{}")
except Exception:
    sys.exit(0)
plan = (data.get("tool_input", {}).get("plan", "")
        or data.get("tool_response", {}).get("result", ""))
if not plan or not plan.strip():
    sys.exit(0)

m = re.search(r'^# (.+)$', plan, re.M)
title = m.group(1).strip() if m else "Untitled plan"
slug = (re.sub(r'[^a-z0-9一-鿿]+', '-', title.lower()).strip('-'))[:60] or "plan"

active = os.environ["ACTIVE_DIR"]
sf = os.environ["STATUS_FIELD"]
date = os.environ["DATE"]
path = os.path.join(active, slug + ".md")

body = f"""# {title}

- **{sf}**: active
- **created**: {date}
- **source**: Claude Code plan mode (ExitPlanMode) — persisted by harness-kit

---

{plan}

---

## Progress log

- `{date}` — plan approved, written to active/

## Decision log

## Definition of Done

- [ ] All steps verified
- [ ] `harness-verify` exits 0
- [ ] Docs updated if affected
- [ ] This plan moved to the completed/ directory
"""
with open(path, "w") as f:
    f.write(body)
sys.stderr.write("[harness-kit] approved plan written to %s\n" % path)
PYEOF
exit 0
