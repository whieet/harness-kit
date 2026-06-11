"""PreToolUse(Edit|Write|MultiEdit) — plan-gate.

When the edited file matches plan.codeGlob
and no active plan covers it, auto-scaffold a plan and inject context.
Non-blocking — does not override the user's permission flow.
"""
from __future__ import annotations

import os
import re

from .. import gitutil, util
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin


def _plugin_root() -> str:
    """Resolve plugin root from HARNESS_KIT_ROOT (set by launcher) or python file."""
    env = os.environ.get("HARNESS_KIT_ROOT")
    if env and os.path.isdir(env):
        return env
    # Fallback: this file is at <root>/scripts/harness/hooks/pre_edit.py.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _slug_for(rel_path: str) -> str:
    s = rel_path.strip()
    s = re.sub(r"\.[^.]+$", "", s)
    s = re.sub(r"[^a-z0-9_/-]", "-", s.lower())
    parts = [p for p in s.split("/") if p]
    out = "-".join(parts[-3:])[:60]
    return out or "session"


def _title_for(rel_path: str) -> str:
    # sed -E 's/\.[^.]+$//; s#/# / #g'
    s = re.sub(r"\.[^.]+$", "", rel_path)
    return s.replace("/", " / ")


def _file_path_from_payload(payload: dict) -> str:
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    fp = ti.get("file_path", "")
    return fp if isinstance(fp, str) else ""


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    if not ctx.cap_enabled("planGate"):
        return 0
    chdir_project(ctx)

    code_glob = ctx.cfg_get_str("plan.codeGlob", "")
    if not code_glob:
        return 0  # plan-gate disabled

    fp = _file_path_from_payload(ctx.payload)
    if not fp:
        return 0
    if not util.regex_search(code_glob, fp):
        return 0

    # Realpath-based relpath: cwd and project root may differ by a symlink
    # (e.g. /var -> /private/var on macOS). Also normalize to forward slashes
    # so the substring check below works consistently on Windows where
    # os.path.relpath returns backslashes.
    try:
        rel_path = os.path.relpath(os.path.realpath(fp), os.path.realpath(ctx.project_dir))
    except ValueError:
        rel_path = fp
    rel_path = rel_path.replace("\\", "/")

    plan_dir = ctx.cfg_get_str("plan.dir", "docs/plans")
    active_dir = os.path.join(plan_dir, "active")

    # Does any active plan already mention this file?
    plans = util.list_plans(active_dir)
    for plan in plans:
        text = util.safe_read(plan)
        if rel_path in text:
            return 0  # covered

    # ---- no covering plan: scaffold one ----
    status_field = ctx.cfg_get_str("plan.statusField", "status")
    template = ctx.cfg_get_str("plan.template", "")
    if not template:
        template = os.path.join(_plugin_root(), "templates", "plan-template.md")
    if not os.path.isfile(template):
        return 0  # nothing to scaffold with

    date = util.date_ymd()
    time_ = util.time_hms_compact()
    timestamp = util.timestamp_minute()
    slug = _slug_for(rel_path)
    title = _title_for(rel_path)

    os.makedirs(active_dir, exist_ok=True)
    # Forward-slash the path we surface to Claude; on Windows os.path.join
    # uses backslashes which look odd in the additionalContext / saved logs.
    plan_file = os.path.join(active_dir, f"auto-{date}-{time_}-{slug}.md").replace("\\", "/")

    tpl = util.safe_read(template)
    source = "plan-gate (auto-created on first edit of `%s` with no covering plan)" % rel_path
    subs = {
        "TITLE": title,
        "STATUS_FIELD": status_field,
        "DATE": date,
        "TIMESTAMP": timestamp,
        "REL_PATH": rel_path,
        "SOURCE": source,
    }
    for k, v in subs.items():
        tpl = tpl.replace("{{%s}}" % k, v)
    util.write_text(plan_file, tpl)

    recent_raw = gitutil.log_oneline(3)
    if recent_raw == "(no commits)":
        recent_block = "  (none)"
    else:
        recent_block = util.indent(recent_raw, "  ")

    ctx_text = (
        f"Auto-created plan: {plan_file}\n"
        f"No active plan covered `{rel_path}`. A scaffold plan was created — fill in its\n"
        "Background, Goals, and Steps, and check off the Definition of Done as you work.\n"
        "The Stop-hook pre-completion gate will verify the DoD before you finish.\n"
        "\n"
        "Recent commits:\n"
        f"{recent_block}"
    )
    util.emit_hook_context("PreToolUse", ctx_text)
    return 0
