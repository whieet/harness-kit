"""harness-check-plan-dod — plan-lifecycle consistency gate."""
from __future__ import annotations

import glob
import os
import re

from .. import util
from ..context import load_context


def run(argv: list[str]) -> int:
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0

    plan = ctx.config.get("plan") or {}
    plan_dir = plan.get("dir", "docs/exec-plans")
    status_field = plan.get("statusField", "status")
    completed_val = plan.get("completedValue", "completed")
    try:
        unchecked_re = re.compile(plan.get("checklistRegex", r"^- \[ \]"))
    except re.error:
        unchecked_re = re.compile(r"^- \[ \]")
    checked_re = re.compile(r"^- \[[xX]\]")
    status_line_re = re.compile(re.escape(status_field) + r"\**\s*[：:]\s*(.+?)\s*$")

    active_dir = os.path.join(plan_dir, "active")
    if not os.path.isdir(active_dir):
        print("  ✓ plan DoD: no active/ dir")
        return 0

    fail = 0
    for path in sorted(glob.glob(os.path.join(active_dir, "*.md"))):
        name = os.path.basename(path)
        if name == ".gitkeep":
            continue
        text = util.safe_read(path)
        lines = text.splitlines()
        status: str | None = None
        for ln in lines:
            m = status_line_re.search(ln)
            if m:
                status = m.group(1).strip().strip("*").strip()
                break
        if status is None:
            continue
        unchecked = sum(1 for ln in lines if unchecked_re.search(ln))
        checked = sum(1 for ln in lines if checked_re.search(ln))
        if status == completed_val:
            print(
                f"  ✗ {name}: status is '{completed_val}' but file is still in active/. "
                "Move it to completed/."
            )
            fail = 1
        elif unchecked == 0 and checked > 0:
            print(
                f"  ✗ {name}: all {checked} DoD items checked but not archived. "
                "Move it to completed/."
            )
            fail = 1

    if fail:
        return 1
    print("  ✓ plan DoD OK")
    return 0
