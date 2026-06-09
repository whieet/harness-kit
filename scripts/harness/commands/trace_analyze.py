"""harness-trace-analyze — post-session analysis + config suggester.

Reads .harness/state/trace.jsonl and .harness/state/loop-*.json. Emits human,
JSON, or suggestion-only output.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

from .. import util
from ..context import HarnessContext, load_context


EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _load_records(state_dir: str) -> list[dict]:
    trace = os.path.join(state_dir, "trace.jsonl")
    if not os.path.isfile(trace):
        return []
    records: list[dict] = []
    for line in util.safe_read(trace).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass
    return records


def _load_churn(state_dir: str) -> Counter:
    churn: Counter = Counter()
    for f in glob.glob(os.path.join(state_dir, "loop-*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(d, dict):
            continue
        for fp, c in d.items():
            try:
                ci = int(c)
            except (TypeError, ValueError):
                continue
            churn[fp] = max(churn[fp], ci)
    return churn


def _analyze(state_dir: str) -> dict:
    records = _load_records(state_dir)
    churn = _load_churn(state_dir)

    started = sum(1 for r in records if r.get("event") == "session_start")
    ended = [r for r in records if r.get("event") == "session_end"]
    passed = sum(1 for r in ended if r.get("result") == "passed")
    failed = sum(1 for r in ended if r.get("result") in ("failed", "advisory_fail"))

    tool_calls = [r for r in records if r.get("event") == "tool_call"]
    tool_fails = [r for r in records if r.get("event") == "tool_fail"]

    # repeated-tool pattern: same tool >=3 consecutive
    seq = [r.get("tool", "") for r in tool_calls]
    repeated: list[str] = []
    i = 0
    while i < len(seq):
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        if seq[i] and (j - i) >= 3 and seq[i] not in repeated:
            repeated.append(seq[i])
        i = j

    # heavy editing per session
    edits_per_session: list[int] = []
    cur = 0
    saw_session = False
    for r in records:
        ev = r.get("event")
        if ev == "session_start":
            if saw_session:
                edits_per_session.append(cur)
            cur, saw_session = 0, True
        elif ev == "tool_call" and r.get("tool") in EDIT_TOOLS:
            cur += 1
    if saw_session:
        edits_per_session.append(cur)
    heavy_sessions = [n for n in edits_per_session if n > 15]

    gate_runs: Counter = Counter()
    gate_fails: Counter = Counter()
    for r in records:
        if r.get("event") == "gate":
            name = r.get("name", "?")
            gate_runs[name] += 1
            if not r.get("ok", True):
                gate_fails[name] += 1

    dim_runs: Counter = Counter()
    dim_low: Counter = Counter()
    for r in records:
        if r.get("event") == "evaluator":
            for dim, score in (r.get("dims") or {}).items():
                dim_runs[dim] += 1
                try:
                    if float(score) < 3:
                        dim_low[dim] += 1
                except (TypeError, ValueError):
                    pass

    signals: list[tuple[str, str, str]] = []
    if started > len(ended) + 2:
        signals.append(
            ("medium", "session_imbalance", f"{started} sessions started vs {len(ended)} ended — possible crashes/interrupts")
        )
    if (passed + failed) > 0 and failed > passed:
        signals.append(
            ("high", "verify_failure_rate", f"{failed} failed vs {passed} passed completion gates — issues caught late")
        )
    if tool_calls and len(tool_fails) * 4 >= len(tool_calls):
        signals.append(
            ("high", "tool_failure_rate", f"{len(tool_fails)} tool failures in {len(tool_calls)} calls — stack/tooling instability")
        )
    for t in repeated:
        signals.append(
            ("medium", "repeated_tool_pattern", f"{t} called >=3x consecutively — possible loop or tool not returning what's expected")
        )
    for fp, c in churn.most_common(10):
        if c >= 5:
            signals.append(("medium", "high_churn", f"{fp} edited {c}x in a session — possible doom loop"))
    if heavy_sessions:
        signals.append(
            ("low", "heavy_editing", f"{len(heavy_sessions)} session(s) with >15 edits — verify incrementally, not all-at-once")
        )

    suggestions: list[str] = []
    for name, runs in gate_runs.items():
        if runs >= 5 and gate_fails[name] == 0:
            suggestions.append(
                f"gate '{name}' failed 0/{runs} runs — if it adds overhead, consider removing it from gates[] or marking tier:fast."
            )
    for dim, runs in dim_runs.items():
        if runs >= 3 and dim_low[dim] * 2 > runs:
            suggestions.append(
                f"evaluator dimension '{dim}' scored <3 in {dim_low[dim]}/{runs} runs — rubric may be too strict, or a real capability gap."
            )
    if any(t for t in repeated):
        suggestions.append(
            "repeated-tool loops seen — consider lowering loopDetection.threshold or adding a gate covering that area."
        )
    if (passed + failed) > 0 and failed > passed:
        suggestions.append(
            "completion gate fails more than it passes — run /harness-kit:verify earlier (mid-task), don't leave it to the Stop gate."
        )

    return {
        "started": started,
        "ended": ended,
        "passed": passed,
        "failed": failed,
        "tool_calls": tool_calls,
        "tool_fails": tool_fails,
        "churn": churn,
        "repeated": repeated,
        "gate_runs": gate_runs,
        "gate_fails": gate_fails,
        "signals": signals,
        "suggestions": suggestions,
    }


def suggest(ctx: HarnessContext) -> list[str]:
    """Lightweight entry used by harness-advisor."""
    return _analyze(ctx.state_dir())["suggestions"]


def run(argv: list[str]) -> int:
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0
    mode = argv[0] if argv else "text"
    result = _analyze(ctx.state_dir())

    if mode == "--suggest":
        for s in result["suggestions"]:
            print(s)
        return 0
    if mode == "--json":
        payload = {
            "sessions_started": result["started"],
            "sessions_ended": len(result["ended"]),
            "gate_passed": result["passed"],
            "gate_failed": result["failed"],
            "tool_calls": len(result["tool_calls"]),
            "tool_fails": len(result["tool_fails"]),
            "top_churn": [{"file": f, "edits": c} for f, c in result["churn"].most_common(10)],
            "repeated_tools": result["repeated"],
            "gate_outcomes": {
                n: {"runs": result["gate_runs"][n], "fails": result["gate_fails"][n]}
                for n in result["gate_runs"]
            },
            "signals": [{"severity": s, "type": t, "detail": d} for s, t, d in result["signals"]],
            "suggestions": result["suggestions"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # human text mode
    print("=== Harness trace analysis ===")
    print(f"  sessions: started={result['started']} ended={len(result['ended'])}")
    print(f"  completion gate: passed={result['passed']} failed={result['failed']}")
    print(f"  tool calls={len(result['tool_calls'])} fails={len(result['tool_fails'])}")
    if result["churn"]:
        print("  most-churned files:")
        for f, c in result["churn"].most_common(5):
            print(f"    {f}: {c}")
    if result["signals"]:
        print("  signals:")
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        for s, t, d in result["signals"]:
            print(f"    {icon.get(s, '⚪')} [{t}] {d}")
    else:
        print("  signals: none — harness running healthy")
    if result["suggestions"]:
        print("  suggestions (you decide):")
        for s in result["suggestions"]:
            print("    - " + s)
    return 0
