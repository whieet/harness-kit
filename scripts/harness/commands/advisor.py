"""harness-advisor — passive harness dashboard.

Port of bin/harness-advisor. The old maturity-phase auto-router is gone;
this just shows metric counts, capability switches, configured gates, and
trace-driven suggestions.
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

from .. import util
from ..context import HarnessContext, load_context

EXPERIMENTAL_OFF = {"evaluatorAutoDispatch"}
KNOWN_CAPS = [
    "planGate",
    "loopDetection",
    "toolTrace",
    "evaluator",
    "contextSnapshot",
    "evaluatorAutoDispatch",
]


def _count_metric(m: dict) -> tuple[str, int] | None:
    name = m.get("name")
    pattern = m.get("glob", "")
    if not name or not pattern:
        return None
    files = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]
    exclude = m.get("exclude")
    if exclude:
        try:
            rx = re.compile(exclude)
            files = [p for p in files if not rx.search(p)]
        except re.error:
            pass
    return name, len(files)


def _suggestions(ctx: HarnessContext) -> list[str]:
    try:
        from . import trace_analyze

        return trace_analyze.suggest(ctx)
    except Exception:  # noqa: BLE001
        return []


def render(ctx: HarnessContext) -> str:
    """Build the dashboard text (used by SessionStart and the CLI)."""
    buf = io.StringIO()

    def emit(s: str = "") -> None:
        buf.write(s + "\n")

    emit("=== Harness dashboard ===")

    # metrics
    counts: dict[str, int] = {}
    for m in ctx.config.get("metrics") or []:
        if not isinstance(m, dict):
            continue
        res = _count_metric(m)
        if res is None:
            continue
        counts[res[0]] = res[1]
    if counts:
        emit("Artifacts: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

    # capabilities
    caps = ctx.config.get("enabledCapabilities") or {}
    shown: list[str] = []
    for name in KNOWN_CAPS:
        default = name not in EXPERIMENTAL_OFF
        on = bool(caps.get(name, default))
        shown.append("%s=%s" % (name, "on" if on else "off"))
    emit("Capabilities: " + ", ".join(shown))
    if "effortRouting" in ctx.config:
        on = bool((ctx.config.get("effortRouting") or {}).get("enabled"))
        emit("Effort routing: " + ("on" if on else "off (always full)"))

    # gates
    gates = ctx.config.get("gates") or []
    if gates:
        labels = []
        for g in gates:
            if not isinstance(g, dict):
                continue
            soft = "" if g.get("blocking", True) else "(soft)"
            labels.append(f"{g.get('name', '?')}{soft}")
        emit("Verify gates: " + ", ".join(labels))

    if ctx.config.get("phases"):
        emit(
            "Note: legacy phases[] is present but IGNORED "
            "(run `claude -p --maintenance` to migrate, or harness-maintenance)."
        )

    suggestions = _suggestions(ctx)
    if suggestions:
        emit("")
        emit("Suggestions (trace-driven — you decide):")
        for s in suggestions:
            emit("  " + s)

    return buf.getvalue().rstrip("\n")


def run(argv: list[str]) -> int:
    """CLI entry. Always emits the dashboard — even with no .harness/config.json,
    matching the bash impl, which printed the header + default capability row
    on uninitialized projects (handy as a status probe in scripts/CI)."""
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        pass  # render() works off ctx.config, not cwd, so continue regardless
    text = render(ctx)
    if text:
        sys.stdout.write(text + "\n")
    return 0
