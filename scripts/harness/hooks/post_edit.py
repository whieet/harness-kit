"""PostToolUse(Edit|Write|MultiEdit) — per-file loop detection.

Port of scripts/on-post-edit.sh. Tracks how many times each file is touched
per session and emits a nudge once any file crosses the threshold. Nudge is
delivered via stderr + exit 2 (PostToolUse: non-blocking, stderr fed to Claude).
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys

from .. import gitutil, util
from ..context import HarnessContext, chdir_project, exit_unless_initialized, load_context, read_stdin

DEFAULT_THRESHOLD = 5


def _session_id(payload: dict) -> str:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    return "default"


def _threshold(ctx: HarnessContext) -> int:
    raw = ctx.cfg_get_str(
        "loopDetection.threshold",
        os.environ.get("CLAUDE_PLUGIN_OPTION_LOOP_THRESHOLD", str(DEFAULT_THRESHOLD)),
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def _ignore_globs(ctx: HarnessContext) -> list[str]:
    raw = (ctx.config.get("loopDetection") or {}).get("ignoreGlobs") or []
    return [g for g in raw if isinstance(g, str) and g]


def _touched_files(diff: str, ignore: list[str]) -> set[str]:
    touched: set[str] = set()
    for line in diff.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        fp = parts[2]
        if any(fnmatch.fnmatch(fp, g) for g in ignore):
            continue
        touched.add(fp)
    return touched


def run() -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    exit_unless_initialized(ctx)
    if not ctx.cap_enabled("loopDetection"):
        return 0
    chdir_project(ctx)

    diff = gitutil.diff_numstat()
    staged = gitutil.diff_staged_numstat()
    if not diff.strip() and not staged.strip():
        return 0

    sid = _session_id(ctx.payload)
    threshold = _threshold(ctx)
    ignore = _ignore_globs(ctx)
    state_file = os.path.join(ctx.state_dir(), f"loop-{sid}.json")

    state: dict[str, int] = {}
    if os.path.isfile(state_file):
        try:
            with open(state_file, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                state = {k: int(v) for k, v in loaded.items() if isinstance(k, str)}
        except (OSError, json.JSONDecodeError, ValueError):
            state = {}

    touched = _touched_files(diff + "\n" + staged, ignore)
    warnings: list[tuple[str, int]] = []
    for fp in touched:
        c = state.get(fp, 0) + 1
        state[fp] = c
        if c >= threshold:
            warnings.append((fp, c))

    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except OSError:
        pass

    if not warnings:
        return 0

    lines: list[str] = []
    for fp, c in warnings:
        lines.append(f"  ⚠️  Loop detection: {fp} edited {c}× this session.")
        lines.append(
            "     Consider: (1) re-read the task spec to confirm the goal; "
            "(2) try a different approach instead of micro-tweaking this file."
        )
    sys.stderr.write("\n".join(lines) + "\n")
    return 2  # PostToolUse: non-blocking nudge, stderr fed to Claude
