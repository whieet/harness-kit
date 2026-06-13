"""Stop — pre-completion verification gate (the "Ralph Loop").

Runs harness-verify + uncommitted check +
active-plan DoD self-check + (optional) evaluator guidance. In verificationMode
== "strict", a failure exits 2 to BLOCK the agent from ending its turn.

All output goes to stderr — Claude Code injects stderr when exit code is 2.
"""
from __future__ import annotations

import os
import re
import sys

from .. import gitutil, util
from ..commands import verify
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin

UNCHECKED_RE = re.compile(r"^- \[ \]")
CHECKED_RE = re.compile(r"^- \[[xX]\]")


def _emit(s: str = "") -> None:
    sys.stderr.write(s + "\n")


def _uncommitted_block() -> tuple[str, str, str]:
    """Returns (changed_head_20, staged_head_20, untracked_head_10) — first lines of each."""
    def head(text: str, n: int) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        return "\n".join(lines[:n])

    ch = head(gitutil.diff_name_only(), 20)
    st = head(gitutil.diff_staged_name_only(), 20)
    un = gitutil.untracked()
    un = "\n".join(line for line in un.splitlines() if not line.endswith(".uid"))
    un = head(un, 10)
    return ch, st, un


def _plan_dod_check(ctx: HarnessContext, plan_dir: str) -> int:
    """Returns 1 if any plan should block, else 0. Writes findings to stderr."""
    _emit(ctx.tr("[3/3] active-plan DoD", "[3/3] active-plan 完成判据"))
    plans = util.list_plans(os.path.join(plan_dir, "active"))
    if not plans:
        _emit(ctx.tr("  (no active plans)", "  （没有进行中的计划）"))
        return 0
    fail = 0
    for plan in plans:
        text = util.safe_read(plan)
        lines = text.splitlines()
        unchecked = sum(1 for ln in lines if UNCHECKED_RE.search(ln))
        checked = sum(1 for ln in lines if CHECKED_RE.search(ln))
        total = unchecked + checked
        name = os.path.basename(plan)
        if total > 0 and unchecked > 0:
            if checked > 0:
                if ctx.language() == "zh":
                    _emit(f"  ❌ {name}: {checked}/{total} 已完成，{unchecked} 未完成 — blocking")
                else:
                    _emit(f"  ❌ {name}: {checked}/{total} done, {unchecked} unfinished — blocking")
                fail = 1
            else:
                if ctx.language() == "zh":
                    _emit(f"  ⚠️  {name}: {unchecked} 项，尚未勾选（可能刚开始）")
                else:
                    _emit(f"  ⚠️  {name}: {unchecked} items, none checked yet (maybe just started)")
        elif total > 0:
            if ctx.language() == "zh":
                _emit(f"  ✓ {name}: 全部 {total} 项已完成")
            else:
                _emit(f"  ✓ {name}: all {total} done")
    return fail


def _evaluator_section(ctx: HarnessContext, changed: str) -> None:
    """Surface the evaluator recipe; never blocks. Effort-aware deferral."""
    if not ctx.cap_enabled("evaluator"):
        return
    code_glob = ctx.cfg_get_str("plan.codeGlob", "")
    if not code_glob:
        return
    if not util.regex_search(code_glob, changed):
        return

    effort = os.environ.get("CLAUDE_EFFORT", "")
    routing_on = ctx.cfg_get_str("effortRouting.enabled", "false") == "true"

    _emit("")
    if routing_on and effort in ("low", "medium"):
        _emit(
            ctx.tr(
                "[evaluator] code changed — deferred at effort=%s (run /harness-kit:evaluate at high effort before final completion).",
                "[evaluator] 代码已改动 — 当前 effort=%s，已延后评估（最终完成前请用 high effort 运行 /harness-kit:evaluate）。",
            ) % effort
        )
        return

    _emit(
        ctx.tr(
            "[evaluator] code changed — run /harness-kit:evaluate (dispatches the evaluator subagent, fresh context) to score this change.",
            "[evaluator] 代码已改动 — 请运行 /harness-kit:evaluate（派出 fresh context 的 evaluator 子代理）为本次改动评分。",
        )
    )
    rubric = ctx.cfg_get_str("evaluator.rubricPath", "")
    if rubric:
        _emit(ctx.tr("  rubric: %s", "  rubric：%s") % rubric)
    _emit(ctx.tr("  verification recipe (dimension → check):", "  验证配方（维度 → 检查）："))
    recipe = ctx.config.get("verificationRecipe") or {}
    if isinstance(recipe, dict):
        for k, v in recipe.items():
            _emit("    - %s: %s" % (k, v))
    _emit(ctx.tr("  any dimension scoring <3 = FAIL → revise before declaring done.", "  任一维度评分 <3 = FAIL → 宣布完成前请先修正。"))


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    chdir_project(ctx)

    mode = ctx.cfg_get_str(
        "verificationMode", os.environ.get("CLAUDE_PLUGIN_OPTION_VERIFICATION_MODE", "strict")
    )
    plan_dir = ctx.cfg_get_str("plan.dir", "docs/plans")
    fail = 0

    _emit(ctx.tr("=== harness-kit: pre-completion gate ===", "=== harness-kit：完成前验证门 ==="))

    # [1] verification orchestrator
    _emit("[1/3] harness-verify")
    vout, vrc = verify.run_capture(ctx)
    _emit(util.indent(vout, "  "))
    if vrc != 0:
        fail = 1

    # [2] uncommitted changes (advisory)
    _emit(ctx.tr("[2/3] uncommitted changes", "[2/3] 未提交改动"))
    ch, st, un = _uncommitted_block()
    if not (ch or st or un):
        _emit(ctx.tr("  ✓ working tree clean", "  ✓ 工作区干净"))
    else:
        _emit(ctx.tr("  ⚠️  uncommitted work present — commit if this is a real milestone", "  ⚠️  存在未提交改动——如果这是一个真实里程碑，请提交"))

    # [3] active-plan DoD self-check
    if _plan_dod_check(ctx, plan_dir) == 1:
        fail = 1

    # optional evaluator
    _evaluator_section(ctx, ch + "\n" + st)

    # trace + verdict
    state_dir = ctx.state_dir()
    if fail and mode == "strict":
        util.append_trace(state_dir, {"event": "session_end", "result": "failed"})
        _emit(
            ctx.tr(
                "=== ❌ pre-completion gate failed — fix the above before finishing (verificationMode=strict) ===",
                "=== ❌ 完成前验证门失败——完成前请先修复以上问题（verificationMode=strict） ===",
            )
        )
        return 2
    result = "advisory_fail" if fail else "passed"
    util.append_trace(state_dir, {"event": "session_end", "result": result})
    if fail:
        _emit(ctx.tr("=== ⚠️  pre-completion gate found issues (advisory mode — not blocking) ===", "=== ⚠️  完成前验证门发现问题（advisory mode——不阻塞） ==="))
    else:
        _emit(ctx.tr("=== ✅ pre-completion gate passed ===", "=== ✅ 完成前验证门通过 ==="))
    return 0
