"""D1+D2+D4: Determinism, idempotency, exit-code contract.

These tests run each hook/command N times against the same fixture and assert:
- D1: stdout/stderr/exit-code are stable across runs
- D2: state mutations are predictable (trace.jsonl gains exactly one record
      per post-tool invocation, plan-gate doesn't re-scaffold)
- D4: NO hook ever returns an unexpected exit code. The documented contract is:
      0=ok, 2=blocking-or-nudge. Anything else = bug. Even on garbage input.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project, run_dispatch


# Number of repetitions for "run-N-times" stability checks.
N = 10


# ---------- D1: deterministic output -----------------------------------------


@pytest.mark.parametrize("dispatch,needs_active_plan", [
    ("session-start", False),
    ("user-prompt", False),  # no dirty marker → empty stdout consistently
    ("pre-edit", False),  # codeGlob empty by default → no-op
    ("post-edit", False),  # no diff → no-op
    ("pre-compact", False),
    ("post-tool", False),  # appends, stdout empty
    ("tool-failure", False),
    ("stop-verify", False),  # all on stderr
])
def test_hook_output_is_deterministic_over_N_runs(tmp_path, dispatch, needs_active_plan):
    """The same payload → the same output, every time (mod the trace timestamp)."""
    proj = make_project(tmp_path)
    payload = json.dumps({"cwd": str(proj), "session_id": "s1"})
    outputs = []
    for _ in range(N):
        r = run_dispatch(dispatch, proj, stdin=payload)
        # Normalize the ISO timestamp the hooks may embed in their output.
        import re
        norm_out = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<ISO>", r.stdout)
        norm_err = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<ISO>", r.stderr)
        outputs.append((r.returncode, norm_out, norm_err))
    first = outputs[0]
    for i, o in enumerate(outputs[1:], 2):
        assert o == first, (
            f"{dispatch}: run #{i} diverged from run #1\n"
            f"  rc: {first[0]} → {o[0]}\n"
            f"  stdout diff: {first[1]!r} vs {o[1]!r}\n"
            f"  stderr diff: {first[2]!r} vs {o[2]!r}"
        )


# ---------- D2: idempotency --------------------------------------------------


def test_pre_edit_does_not_duplicate_scaffold(tmp_path):
    """Running pre-edit twice for the same uncovered file → still ONE plan
    (the second run sees the just-created plan and treats it as covering)."""
    proj = make_project(tmp_path, extra_config={"plan": {"codeGlob": r"\.py$"}})
    (proj / "src").mkdir()
    f = proj / "src" / "x.py"
    f.write_text("a=1\n", encoding="utf-8")
    payload = json.dumps({
        "cwd": str(proj),
        "session_id": "s",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(f)},
    })
    for _ in range(5):
        r = run_dispatch("pre-edit", proj, stdin=payload)
        assert r.returncode == 0
    plans = list((proj / "docs" / "plans" / "active").glob("auto-*.md"))
    assert len(plans) == 1, f"pre-edit should scaffold ONCE; got {[p.name for p in plans]}"


def test_post_tool_appends_exactly_one_record_per_call(tmp_path):
    """N invocations → N records (no duplicates, no drops)."""
    proj = make_project(tmp_path)
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "file_path": "/tmp/x"},
    })
    for i in range(N):
        r = run_dispatch("post-tool", proj, stdin=payload)
        assert r.returncode == 0, f"run #{i}: rc={r.returncode}"
    trace = (proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8")
    lines = [l for l in trace.splitlines() if l.strip()]
    assert len(lines) == N, f"expected {N} trace records, got {len(lines)}"
    for line in lines:
        rec = json.loads(line)
        assert rec["event"] == "tool_call"
        assert rec["tool"] == "Bash"


def test_user_prompt_clears_dirty_marker_exactly_once(tmp_path):
    """Two user-prompt calls in a row: first injects + clears, second silent."""
    proj = make_project(tmp_path)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "pre-compact-snapshot.json").write_text(json.dumps({
        "ts": "2025-01-01T00:00:00Z",
        "plans": [],
        "lastGateResult": "passed",
        "recentFailedGates": [],
    }), encoding="utf-8")
    (state / "pre-compact.dirty").write_text("", encoding="utf-8")
    payload = json.dumps({"cwd": str(proj)})
    r1 = run_dispatch("user-prompt", proj, stdin=payload)
    assert r1.returncode == 0
    assert "additionalContext" in r1.stdout
    assert not (state / "pre-compact.dirty").exists()
    r2 = run_dispatch("user-prompt", proj, stdin=payload)
    assert r2.returncode == 0
    assert r2.stdout.strip() == "", "second call should be a no-op"


def test_pre_compact_overwrites_snapshot_cleanly(tmp_path):
    """Running pre-compact twice → snapshot reflects the LATEST state, dirty marker present."""
    proj = make_project(tmp_path)
    payload = json.dumps({"cwd": str(proj)})
    # First snapshot: no active plans
    r1 = run_dispatch("pre-compact", proj, stdin=payload)
    assert r1.returncode == 0
    snap_path = proj / ".harness" / "state" / "pre-compact-snapshot.json"
    snap1 = json.loads(snap_path.read_text(encoding="utf-8"))
    assert snap1["plans"] == []
    # Now add a plan with partial DoD and snapshot again
    (proj / "docs" / "plans" / "active" / "p.md").write_text(
        "# p\n- [x] one\n- [ ] two\n", encoding="utf-8")
    r2 = run_dispatch("pre-compact", proj, stdin=payload)
    assert r2.returncode == 0
    snap2 = json.loads(snap_path.read_text(encoding="utf-8"))
    assert snap2["plans"] == [{"name": "p.md", "checked": 1, "total": 2}]
    # Timestamp should be different (or at least snapshot replaced cleanly)
    assert (proj / ".harness" / "state" / "pre-compact.dirty").exists()


# ---------- D4: exit-code contract under garbage input -----------------------


@pytest.mark.parametrize("dispatch", [
    "session-start", "user-prompt", "pre-edit", "post-edit",
    "plan-approved", "post-tool", "tool-failure", "pre-compact",
])
@pytest.mark.parametrize("payload,desc", [
    ("", "empty stdin"),
    ("not json", "garbage non-JSON"),
    ("{}", "valid but empty JSON"),
    ('{"cwd": "/nonexistent/path"}', "nonexistent cwd"),
    ('{"cwd": null}', "null cwd"),
    ('{"tool_input": "not a dict"}', "wrong type for tool_input"),
    ('{"tool_input": {"file_path": null}}', "null file_path"),
    ('{"tool_input": {"file_path": 123}}', "non-string file_path"),
    ('{"session_id": null}', "null session_id"),
    ('{"session_id": ["not", "a", "string"]}', "non-string session_id"),
    (json.dumps({"cwd": "/tmp", "session_id": "s"} | ({"tool_input": {"file_path": "/etc/hosts"}} if False else {})), "minimal valid"),
    # very large payload to stress json parsing
    (json.dumps({"cwd": "/tmp", "garbage": "x" * 100_000}), "100KB extra fields"),
    # unicode field values
    (json.dumps({"cwd": "/tmp", "tool_name": "测试工具", "tool_input": {"file_path": "/路径/文件.py"}}), "unicode"),
    # nested arrays
    (json.dumps({"cwd": "/tmp", "tool_input": [1, 2, 3]}), "array instead of dict"),
])
def test_hook_never_crashes_on_bad_input(tmp_path, dispatch, payload, desc):
    """A hook MUST NOT return a code other than 0 or 2 on any input — that
    would surface as a Claude Code error in the user's terminal. Pythonic
    'raise SystemExit(1)' or unhandled exceptions both violate this."""
    proj = make_project(tmp_path)
    r = run_dispatch(dispatch, proj, stdin=payload)
    assert r.returncode in (0, 2), (
        f"{dispatch} ({desc}): exit code {r.returncode} not in contract\n"
        f"stderr: {r.stderr[:500]}\nstdout: {r.stdout[:500]}"
    )
    # No Python tracebacks should leak to stderr
    assert "Traceback" not in r.stderr, (
        f"{dispatch} ({desc}): leaked traceback:\n{r.stderr[:500]}"
    )


# ---------- D8: resource cleanup ---------------------------------------------


def test_no_lingering_temp_files(tmp_path):
    """Run several hooks; ensure no tempfiles named harness-* persist in $TMPDIR."""
    import glob

    proj = make_project(tmp_path)
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    before = set(glob.glob(os.path.join(tmpdir, "*")))
    payload = json.dumps({"cwd": str(proj), "session_id": "s"})
    for d in ("session-start", "user-prompt", "pre-compact", "post-tool",
              "tool-failure", "pre-edit", "post-edit"):
        run_dispatch(d, proj, stdin=payload)
    after = set(glob.glob(os.path.join(tmpdir, "*")))
    new_tmpfiles = [p for p in (after - before) if "harness" in p.lower() or "tmp" in os.path.basename(p)]
    # Only "harness"-tagged tempfiles matter — other unrelated tmpfiles are noise.
    suspicious = [p for p in new_tmpfiles if "harness" in os.path.basename(p).lower()]
    assert not suspicious, f"hooks leaked tempfiles: {suspicious}"
