"""PostToolUseFailure(*) — async, lightweight failure tracer."""
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
    if not isinstance(tool, str) or not tool:
        return 0
    rec: dict = {"event": "tool_fail", "tool": tool}
    for k in ("exit_code", "error_message"):
        if k in ctx.payload:
            rec[k] = ctx.payload[k]
    util.append_trace(ctx.state_dir(), rec)
    return 0
