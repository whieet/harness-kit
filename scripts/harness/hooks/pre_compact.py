"""PreCompact — snapshot harness state so it survives context compaction.

Pairs with on-user-prompt (re-injects once after compaction) and on-session-start
(surfaces on resume). PostCompact additionalContext is not supported, so the
snapshot + dirty marker are the supported recovery path.
"""
from __future__ import annotations

import glob
import json
import os
import re

from .. import util
from ..context import chdir_project, exit_unless_initialized, load_context, read_stdin

UNCHECKED_RE = re.compile(r"^- \[ \]")
CHECKED_RE = re.compile(r"^- \[[xX]\]")


def _scan_active_plans(active_dir: str) -> list[dict]:
    plans: list[dict] = []
    if not os.path.isdir(active_dir):
        return plans
    for path in sorted(glob.glob(os.path.join(active_dir, "*.md"))):
        if os.path.basename(path) == ".gitkeep":
            continue
        try:
            lines = util.safe_read(path).splitlines()
        except OSError:
            continue
        unchecked = sum(1 for ln in lines if UNCHECKED_RE.search(ln))
        checked = sum(1 for ln in lines if CHECKED_RE.search(ln))
        if unchecked + checked > 0:
            plans.append(
                {
                    "name": os.path.basename(path),
                    "checked": checked,
                    "total": unchecked + checked,
                }
            )
    return plans


def _scan_trace(state_dir: str) -> tuple[str | None, list[str]]:
    trace = os.path.join(state_dir, "trace.jsonl")
    if not os.path.isfile(trace):
        return None, []
    recs: list[dict] = []
    try:
        for line in util.safe_read(trace).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        return None, []

    last_result: str | None = None
    for r in reversed(recs):
        if r.get("event") == "session_end":
            last_result = r.get("result")
            break

    recent_fail: list[str] = []
    for r in recs[-60:]:
        if r.get("event") == "gate" and not r.get("ok", True):
            name = r.get("name")
            if isinstance(name, str):
                recent_fail.append(name)
    return last_result, recent_fail


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    if not ctx.cap_enabled("contextSnapshot"):
        return 0
    chdir_project(ctx)

    state = ctx.state_dir()
    plan_dir = ctx.cfg_get_str("plan.dir", "docs/plans")
    active_dir = os.path.join(plan_dir, "active")

    plans = _scan_active_plans(active_dir)
    last_result, recent_fail = _scan_trace(state)
    # Dedup preserving order, then keep the last 5.
    deduped: list[str] = []
    seen: set[str] = set()
    for n in recent_fail:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    snap = {
        "ts": util.iso_utc(),
        "plans": plans,
        "lastGateResult": last_result,
        "recentFailedGates": deduped[-5:],
    }
    try:
        with open(os.path.join(state, "pre-compact-snapshot.json"), "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False)
        # Touch the dirty marker.
        open(os.path.join(state, "pre-compact.dirty"), "w", encoding="utf-8").close()
    except OSError:
        pass
    return 0
