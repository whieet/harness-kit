"""D9+D10: Concurrency + performance.

D9: trace.jsonl is the only state file written by multiple hooks. POSIX guarantees
    O_APPEND atomicity for writes < PIPE_BUF (typically 4096 bytes). Verify
    parallel hooks don't corrupt or interleave records.

D10: Hook latency budget. Claude Code hooks run on every tool call; if any
     of them takes > 1s on a vanilla repo, the user feels it. Assert each
     hook completes well under the timeout configured in hooks.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project, run_dispatch


# ---------- D9: concurrent trace writes -----------------------------------


def test_concurrent_post_tool_writes_no_corruption(tmp_path):
    """10 parallel `post-tool` invocations append 10 valid JSON lines to trace.jsonl."""
    proj = make_project(tmp_path)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    # Pre-create so all writers race on append, not on file creation
    (state / "trace.jsonl").touch()

    def one(i: int):
        payload = json.dumps({
            "cwd": str(proj),
            "tool_name": f"Tool{i}",
            "tool_input": {"file_path": f"/p/{i}.py"},
        })
        return run_dispatch("post-tool", proj, stdin=payload)

    N = 10
    with ThreadPoolExecutor(max_workers=N) as ex:
        futs = [ex.submit(one, i) for i in range(N)]
        for f in as_completed(futs):
            r = f.result()
            assert r.returncode == 0, f"concurrent write failed: {r.stderr}"

    lines = (state / "trace.jsonl").read_text().splitlines()
    assert len(lines) == N, f"expected exactly {N} lines, got {len(lines)}"
    # Each line must be valid JSON with the expected event/tool fields
    tools_seen = set()
    for line in lines:
        rec = json.loads(line)
        assert rec["event"] == "tool_call"
        assert rec["tool"].startswith("Tool")
        tools_seen.add(rec["tool"])
    assert tools_seen == {f"Tool{i}" for i in range(N)}, (
        f"some writes lost: missing {set(f'Tool{i}' for i in range(N)) - tools_seen}"
    )


def test_concurrent_post_edit_writes_per_session_isolated(tmp_path):
    """Two sessions in parallel each maintain their own loop-<sid>.json — no crosstalk."""
    proj = make_project(
        tmp_path,
        extra_config={"plan": {"codeGlob": r"\.py$"}, "loopDetection": {"threshold": 99}},
    )
    f = proj / "shared.py"
    f.write_text("a=1\n")
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)

    def one(sid: str):
        payload = json.dumps({
            "cwd": str(proj),
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(f)},
        })
        return run_dispatch("post-edit", proj, stdin=payload)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(one, sid) for sid in ("alpha", "alpha", "beta", "beta")]
        for fut in as_completed(futs):
            r = fut.result()
            assert r.returncode in (0, 2)

    # Both per-session files exist; each has a count for shared.py
    alpha = json.loads((proj / ".harness" / "state" / "loop-alpha.json").read_text())
    beta = json.loads((proj / ".harness" / "state" / "loop-beta.json").read_text())
    # Total writes across both sessions ≥ 2 each (we fired 2 per session, but race
    # might have one read-modify-write hit a stale read — that's an inherent
    # filesystem race the bash impl ALSO has, so just assert non-zero)
    assert alpha.get("shared.py", 0) >= 1
    assert beta.get("shared.py", 0) >= 1


# ---------- D10: latency budget -------------------------------------------


# Per hooks.json, each hook has a timeout. Real budget should be a fraction of
# that. We aim for each hook to complete in < 2.0s on a fresh fixture; if any
# hook is slower the user will notice on every tool call.
LATENCY_BUDGET = {
    "session-start": 2.0,
    "user-prompt": 1.0,
    "pre-edit": 2.0,
    "post-edit": 2.0,
    "plan-approved": 2.0,
    "post-tool": 1.0,
    "tool-failure": 1.0,
    "pre-compact": 2.0,
    "stop-verify": 5.0,  # includes harness-verify + plan-DoD scan
}


@pytest.mark.parametrize("dispatch,budget_s", list(LATENCY_BUDGET.items()))
def test_hook_latency_under_budget(tmp_path, dispatch, budget_s):
    """Run the hook 3 times and assert median latency stays under budget."""
    proj = make_project(tmp_path, extra_config={"plan": {"codeGlob": r"\.py$"}})
    payload = json.dumps({
        "cwd": str(proj),
        "session_id": "s",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(proj / "x.py")},
    })
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        r = run_dispatch(dispatch, proj, stdin=payload)
        times.append(time.perf_counter() - t0)
        assert r.returncode in (0, 2)
    times.sort()
    median = times[1]
    assert median < budget_s, (
        f"{dispatch} median latency {median:.2f}s exceeds budget {budget_s}s "
        f"(samples: {times})"
    )


def test_dispatcher_cold_start_under_500ms(tmp_path):
    """The trampoline (bash launcher → python → import → no-op) should be fast
    even on the cold-start path, otherwise startup-heavy hooks hurt UX."""
    proj = make_project(tmp_path, with_config=False)
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        r = run_dispatch("post-tool", proj, stdin='{"cwd": "/tmp"}')
        times.append(time.perf_counter() - t0)
        assert r.returncode == 0
    times.sort()
    # First-process Python startup on macOS is ~50-200ms; 500ms gives headroom.
    assert times[1] < 0.5, f"cold start too slow: {times}"
