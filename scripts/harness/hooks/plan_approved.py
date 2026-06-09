"""PostToolUse(ExitPlanMode) — persist the approved plan to disk.

Port of scripts/on-plan-approved.sh. Captures tool_input.plan or
tool_response.result into the configured plan directory with metadata
and a DoD stub. Prints the path to stderr (non-blocking notice).
"""
from __future__ import annotations

import os
import re
import sys

from .. import util
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin


def _extract_plan(payload: dict) -> str:
    """Try tool_input.plan first, then tool_response.result (both are documented).

    Returns the raw plan text (not stripped) — the bash impl persisted the
    plan verbatim into the saved file body, only checking `.strip()` for the
    empty-guard. Stripping here would silently rewrite the saved markdown.

    Defensive: tool_input or tool_response may be a non-dict (e.g. malformed
    payload, plain string). Treat any non-dict as missing.
    """
    ti = payload.get("tool_input")
    if isinstance(ti, dict):
        raw = ti.get("plan", "")
        if isinstance(raw, str) and raw.strip():
            return raw
    tr = payload.get("tool_response")
    if isinstance(tr, dict):
        raw = tr.get("result", "")
        if isinstance(raw, str) and raw.strip():
            return raw
    return ""


def _make_slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9一-鿿]+", "-", title.lower()).strip("-")
    return s[:60] or "plan"


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    chdir_project(ctx)

    plan = _extract_plan(ctx.payload)
    if not plan:
        return 0

    plan_dir = ctx.cfg_get_str("plan.dir", "docs/exec-plans")
    status_field = ctx.cfg_get_str("plan.statusField", "status")
    active_dir = os.path.join(plan_dir, "active")
    os.makedirs(active_dir, exist_ok=True)

    date = util.date_ymd()

    # Extract first h1 for the title
    m = re.search(r"^# (.+)$", plan, re.MULTILINE)
    title = m.group(1).strip() if m else "Untitled plan"
    slug = _make_slug(title)

    body = f"""# {title}

- **{status_field}**: active
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

    path = os.path.join(active_dir, slug + ".md")
    util.write_text(path, body)
    sys.stderr.write("[harness-kit] approved plan written to %s\n" % path)
    return 0