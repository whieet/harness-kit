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

    parts = [ctx.tr("Harness state carried across compaction:", "跨上下文压缩保留的 Harness 状态：")]
    parts.append(ctx.language_directive())
    plans = s.get("plans") or []
    for p in plans:
        parts.append(
            ctx.tr("  - active plan %s: %d/%d DoD checked", "  - active plan %s：%d/%d 完成判据已勾选")
            % (p.get("name", "?"), p.get("checked", 0), p.get("total", 0))
        )
    if not plans:
        parts.append(ctx.tr("  - no active plans", "  - 没有进行中的计划"))
    if s.get("lastGateResult"):
        parts.append(ctx.tr("  - last completion gate: %s", "  - 上次完成门结果：%s") % s["lastGateResult"])
    failed = s.get("recentFailedGates") or []
    if failed:
        parts.append(ctx.tr("  - recently failing gates: %s", "  - 最近失败的门禁：%s") % ", ".join(failed))
    parts.append(ctx.tr("Finish the unchecked DoD items and pass the gates before declaring done.", "宣布完成前，先完成未勾选的完成判据并通过门禁。"))
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
