"""PostToolUse(*) — async, lightweight tool-call tracer."""
from __future__ import annotations

from .. import util
from ..context import chdir_project, exit_unless_initialized, load_context, read_stdin


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    if not ctx.cap_enabled("toolTrace"):
        return 0
    chdir_project(ctx)

    tool = ctx.payload.get("tool_name", "")
    if not isinstance(tool, str):
        return 0
    if not tool:
        return 0
    ti = ctx.payload.get("tool_input")
    fp = ""
    if isinstance(ti, dict):
        v = ti.get("file_path", "")
        if isinstance(v, str):
            fp = v

    rec: dict = {"event": "tool_call", "tool": tool}
    if fp:
        rec["file"] = fp
    util.append_trace(ctx.state_dir(), rec)
    return 0
