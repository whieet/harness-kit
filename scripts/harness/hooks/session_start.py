"""SessionStart — inject a session handoff as additionalContext.

Composes: git state + active plans +
harness-advisor dashboard + config-driven key-docs + a generic checklist.
Also clears the pre-compact dirty marker (session start supersedes the
mid-session re-inject) and appends a session_start trace event.
"""
from __future__ import annotations

import json
import os

from .. import gitutil, util
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin


def _resume_block(ctx: HarnessContext) -> str:
    """Surface unfinished work from a pre-compaction snapshot."""
    if not ctx.cap_enabled("contextSnapshot"):
        return ""
    snap_path = os.path.join(ctx.state_dir(), "pre-compact-snapshot.json")
    if not os.path.isfile(snap_path):
        return ""
    try:
        with open(snap_path, encoding="utf-8") as fh:
            snap = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return ""
    plans = snap.get("plans") or []
    incomplete = [p for p in plans if p.get("checked", 0) < p.get("total", 0)]
    last = snap.get("lastGateResult")
    if not incomplete and last not in ("failed", "advisory_fail"):
        return ""
    out = [ctx.tr("Resuming — unfinished from before:", "恢复上次未完成的工作：")]
    for p in incomplete:
        out.append(
            ctx.tr("  - %s: %d/%d DoD", "  - %s：%d/%d 完成判据")
            % (p.get("name", "?"), p.get("checked", 0), p.get("total", 0))
        )
    failed_gates = snap.get("recentFailedGates") or []
    if failed_gates:
        out.append(ctx.tr("  - recently failing gates: ", "  - 最近失败的门禁：") + ", ".join(failed_gates))
    return "\n".join(out)


def _advisor_output(ctx: HarnessContext) -> str:
    """Run the advisor in-process (used to shell out to `bash bin/harness-advisor`).

    Returns "" if the advisor module fails for any reason — never fatal.
    """
    try:
        from ..commands import advisor

        return advisor.render(ctx)
    except Exception:  # noqa: BLE001 - never fail the session start
        return ""


def _key_docs(ctx: HarnessContext) -> str:
    rows = (ctx.config.get("docs") or {}).get("keyDocs") or []
    lines: list[str] = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        lines.append("- %s — %s" % (d.get("path", ""), d.get("note", "")))
    return "\n".join(lines)


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    chdir_project(ctx)

    plan_dir = ctx.cfg_get_str("plan.dir", "docs/plans")
    active_dir = os.path.join(plan_dir, "active")

    branch = gitutil.branch()
    uncommitted = gitutil.count_lines(gitutil.diff_name_only())
    untracked = gitutil.count_lines(gitutil.untracked())
    recent = gitutil.log_oneline(5)

    plans = util.list_plans(active_dir)
    active_count = len(plans)

    advisor_out = _advisor_output(ctx)
    key_docs = _key_docs(ctx)
    resume = _resume_block(ctx)

    parts: list[str] = []
    parts.append(ctx.tr("=== Session Handoff (harness-kit) ===", "=== Session Handoff (harness-kit) / 会话交接 ==="))
    parts.append(ctx.language_directive())
    parts.append("")
    if advisor_out:
        parts.append(advisor_out)
        parts.append("")
    parts.append(ctx.tr("Git: branch=%s, uncommitted=%d, untracked=%d", "Git：branch=%s，未提交=%d，未跟踪=%d") % (branch, uncommitted, untracked))
    parts.append(ctx.tr("Recent commits:", "最近提交："))
    parts.append(recent)
    parts.append("")
    parts.append(ctx.tr("Active plans (%d):", "进行中的计划（%d）：") % active_count)
    if active_count > 0:
        for p in plans:
            parts.append("  " + p)
    else:
        parts.append(ctx.tr("  (none — create one before editing planned code)", "  （无——编辑受计划管控的代码前请先创建计划）"))
    if key_docs:
        parts.append("")
        parts.append(ctx.tr("Key docs:", "关键文档："))
        parts.append(key_docs)
    if resume:
        parts.append("")
        parts.append(resume)
    parts.append("")
    parts.append(ctx.tr("Harness (auto via plugin hooks — you do not run these): SessionStart handoff;", "Harness（由插件 hook 自动执行——你不需要手动运行）：SessionStart 会话交接；"))
    parts.append(ctx.tr("PreToolUse plan-gate; PostToolUse loop-detect; Stop pre-completion verify gate.", "PreToolUse 计划门；PostToolUse 循环检测；Stop 完成前验证门。"))

    # Session start supersedes the mid-session re-inject; clear the dirty marker.
    dirty = os.path.join(ctx.state_dir(), "pre-compact.dirty")
    try:
        if os.path.exists(dirty):
            os.remove(dirty)
    except OSError:
        pass

    # Emit with a trailing newline so additionalContext ends cleanly (some
    # consumers expect the injected block to be newline-terminated).
    util.emit_hook_context("SessionStart", "\n".join(parts) + "\n")
    util.append_trace(ctx.state_dir(), {"event": "session_start"})
    return 0
