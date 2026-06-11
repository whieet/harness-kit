"""UserPromptSubmit — re-inject harness state once after a compaction.

PreCompact wrote a snapshot + a `dirty`
marker; if the marker exists, emit one additionalContext block and clear the
marker so it injects exactly once. Gated by capability `contextSnapshot`.
"""
from __future__ import annotations

import json
import os

from .. import util
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin


def _build_context(ctx: HarnessContext) -> str:
    state = ctx.state_dir()
    snap_path = os.path.join(state, "pre-compact-snapshot.json")
    if not os.path.isfile(snap_path):
        return ""
    try:
        with open(snap_path, encoding="utf-8") as fh:
            s = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return ""

    parts = ["Harness state carried across compaction:"]
    plans = s.get("plans") or []
    for p in plans:
        parts.append(
            "  - active plan %s: %d/%d DoD checked"
            % (p.get("name", "?"), p.get("checked", 0), p.get("total", 0))
        )
    if not plans:
        parts.append("  - no active plans")
    if s.get("lastGateResult"):
        parts.append("  - last completion gate: %s" % s["lastGateResult"])
    failed = s.get("recentFailedGates") or []
    if failed:
        parts.append("  - recently failing gates: %s" % ", ".join(failed))
    parts.append("Finish the unchecked DoD items and pass the gates before declaring done.")
    return "\n".join(parts)


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    if not ctx.cap_enabled("contextSnapshot"):
        return 0
    chdir_project(ctx)

    dirty = os.path.join(ctx.state_dir(), "pre-compact.dirty")
    if not os.path.isfile(dirty):
        return 0  # nothing to recover

    text = _build_context(ctx)

    # Clear the marker BEFORE emitting so a crash after this point still
    # progresses (rm before emit, not after).
    try:
        os.remove(dirty)
    except OSError:
        pass

    if text:
        util.emit_hook_context("UserPromptSubmit", text)
    return 0
