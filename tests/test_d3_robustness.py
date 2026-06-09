"""D3+D5+D6: Input robustness — unicode, weird paths, weird git states.

First-principles tests for things that *can* crash a hook but that the
existing test suite never exercises because all fixtures are vanilla
ASCII-named git repos."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, run_dispatch


def _mkrepo(parent: Path, name: str = "proj", make_commit: bool = True) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    proj = parent / name
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    if make_commit:
        (proj / "README.md").write_text("# r\n")
        subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
        subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "init"], check=True)
    return proj


def _harness_init(proj: Path, **cfg_overrides) -> None:
    h = proj / ".harness"
    h.mkdir(exist_ok=True)
    base = {
        "projectType": "custom",
        "verificationMode": "strict",
        "gates": [],
        "plan": {"dir": "docs/plans", "codeGlob": r"\.py$"},
        "docs": {"scanRoots": ["docs"]},
        "metrics": [],
        "loopDetection": {"threshold": 3},
        "enabledCapabilities": {
            "planGate": True, "loopDetection": True, "toolTrace": True,
            "evaluator": True, "contextSnapshot": True, "evaluatorAutoDispatch": False,
        },
    }
    base.update(cfg_overrides)
    (h / "config.json").write_text(json.dumps(base))
    for sub in ("active", "completed"):
        d = proj / "docs" / "plans" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()


# ---------- D5: paths with spaces, unicode, weird chars ---------------------


def test_project_path_with_spaces(tmp_path):
    proj = _mkrepo(tmp_path / "a b c")
    _harness_init(proj)
    payload = json.dumps({"cwd": str(proj), "session_id": "s"})
    r = run_dispatch("session-start", proj, stdin=payload)
    assert r.returncode == 0, f"path with spaces broke session-start\n{r.stderr}"
    out = json.loads(r.stdout.strip())
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_project_path_with_unicode(tmp_path):
    proj = _mkrepo(tmp_path / "目录-emoji-🚀")
    _harness_init(proj)
    payload = json.dumps({"cwd": str(proj), "session_id": "s"}, ensure_ascii=False)
    r = run_dispatch("session-start", proj, stdin=payload)
    assert r.returncode == 0, f"unicode path broke session-start\n{r.stderr}"


def test_file_path_with_unicode_in_pre_edit(tmp_path):
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    src = proj / "源码"
    src.mkdir()
    f = src / "测试.py"
    f.write_text("x=1\n", encoding="utf-8")
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(f)},
    }, ensure_ascii=False)
    r = run_dispatch("pre-edit", proj, stdin=payload)
    assert r.returncode == 0, f"unicode file path broke pre-edit\n{r.stderr}"
    plans = list((proj / "docs" / "plans" / "active").glob("auto-*.md"))
    assert len(plans) == 1
    # Plan body should contain the unicode path
    body = plans[0].read_text(encoding="utf-8")
    assert "源码/测试.py" in body or "测试" in body


def test_plan_with_unicode_title(tmp_path):
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    plan = "# 中文计划标题 🎯\n\n做一件事。\n"
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "ExitPlanMode",
        "tool_input": {"plan": plan},
    }, ensure_ascii=False)
    r = run_dispatch("plan-approved", proj, stdin=payload)
    assert r.returncode == 0, r.stderr
    files = [p for p in (proj / "docs" / "plans" / "active").iterdir()
             if p.suffix == ".md" and p.name != ".gitkeep"]
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "中文计划标题" in body


def test_config_with_unicode_status_field(tmp_path):
    """A Chinese statusField (the godot template ships with '状态') must work."""
    proj = _mkrepo(tmp_path)
    _harness_init(proj, plan={
        "dir": "docs/plans",
        "codeGlob": r"\.py$",
        "statusField": "状态",
        "completedValue": "completed",
    })
    # Create a completed-but-not-archived plan to trigger plan-dod
    (proj / "docs" / "plans" / "active" / "p.md").write_text(
        "# p\n- **状态**: completed\n- [x] one\n", encoding="utf-8"
    )
    r = run_dispatch("harness-check-plan-dod", proj)
    assert r.returncode == 1, f"unicode statusField didn't flag; stdout={r.stdout}"
    assert "p.md" in r.stdout


# ---------- D6: weird git states ---------------------------------------------


def test_no_commits_yet(tmp_path):
    """Brand new repo, no commits. session-start, post-edit etc. must not crash."""
    proj = _mkrepo(tmp_path, make_commit=False)
    _harness_init(proj)
    payload = json.dumps({"cwd": str(proj), "session_id": "s"})
    r = run_dispatch("session-start", proj, stdin=payload)
    assert r.returncode == 0, f"no-commits repo broke session-start\n{r.stderr}"


def test_detached_head(tmp_path):
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    # Make a second commit then check out the first one (detached)
    (proj / "x.txt").write_text("1\n")
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "second"], check=True)
    first = subprocess.run(
        ["git", "-C", str(proj), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(proj), "checkout", "-q", first], check=True)
    payload = json.dumps({"cwd": str(proj), "session_id": "s"})
    r = run_dispatch("session-start", proj, stdin=payload)
    assert r.returncode == 0


def test_path_outside_git(tmp_path):
    """No git at all — most hooks should still work (config-based, not git-based)."""
    proj = tmp_path / "nogit"
    proj.mkdir()
    _harness_init(proj)
    payload = json.dumps({"cwd": str(proj), "session_id": "s"})
    r = run_dispatch("session-start", proj, stdin=payload)
    # Should still emit a SessionStart context (branch will say "unknown")
    assert r.returncode == 0, f"non-git project broke session-start\n{r.stderr}"
    out = json.loads(r.stdout.strip())
    assert "unknown" in out["hookSpecificOutput"]["additionalContext"]


# ---------- D3: corrupt state files -----------------------------------------


def test_corrupt_trace_jsonl(tmp_path):
    """A line that isn't valid JSON in trace.jsonl must not crash trace-analyze."""
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "trace.jsonl").write_text(
        '{"event":"session_start"}\n'
        'this is not json\n'
        '{"event":"session_end","result":"passed"}\n'
        '\n'  # blank line
        'random garbage\n'
    )
    r = run_dispatch("harness-trace-analyze", proj)
    assert r.returncode == 0, f"corrupt trace crashed trace-analyze\n{r.stderr}"
    # The valid records should still count
    assert "started=1" in r.stdout
    assert "passed=1" in r.stdout


def test_corrupt_config_json(tmp_path):
    """A malformed config.json: maintenance should report cleanly, hooks should no-op."""
    proj = _mkrepo(tmp_path)
    (proj / ".harness").mkdir()
    (proj / ".harness" / "config.json").write_text("not valid json {")
    r = run_dispatch("harness-maintenance", proj)
    assert r.returncode == 0
    assert "INVALID JSON" in r.stdout
    # Hooks should treat malformed config as effectively no-config and exit 0 silently
    r2 = run_dispatch("session-start", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r2.returncode == 0, f"corrupt config broke session-start\n{r2.stderr}"


def test_corrupt_loop_state_file(tmp_path):
    """A corrupt loop-*.json file should not crash post-edit or trace-analyze."""
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "loop-default.json").write_text("not json")
    f = proj / "x.py"
    f.write_text("a=1\n")
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    payload = json.dumps({
        "cwd": str(proj), "session_id": "default", "tool_name": "Edit",
        "tool_input": {"file_path": str(f)},
    })
    r = run_dispatch("post-edit", proj, stdin=payload)
    assert r.returncode in (0, 2)  # may nudge or not, but not crash


def test_corrupt_snapshot_json(tmp_path):
    """A corrupt pre-compact-snapshot.json should not crash user-prompt / session-start."""
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "pre-compact-snapshot.json").write_text("not json")
    (state / "pre-compact.dirty").write_text("")
    payload = json.dumps({"cwd": str(proj)})
    r = run_dispatch("user-prompt", proj, stdin=payload)
    assert r.returncode == 0
    # Marker should still be cleared so we don't keep re-trying a broken snapshot
    assert not (state / "pre-compact.dirty").exists()


# ---------- D3: missing required fields ------------------------------------


def test_plan_approved_with_no_plan(tmp_path):
    """tool_input.plan missing AND tool_response.result missing → no file written."""
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "ExitPlanMode",
        "tool_input": {},  # no 'plan' key
    })
    r = run_dispatch("plan-approved", proj, stdin=payload)
    assert r.returncode == 0
    files = [p for p in (proj / "docs" / "plans" / "active").iterdir()
             if p.suffix == ".md" and p.name != ".gitkeep"]
    assert files == [], f"no plan → no file; got {files}"


def test_pre_edit_with_no_file_path(tmp_path):
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Edit",
        "tool_input": {},  # no file_path
    })
    r = run_dispatch("pre-edit", proj, stdin=payload)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_post_tool_with_no_tool_name(tmp_path):
    proj = _mkrepo(tmp_path)
    _harness_init(proj)
    payload = json.dumps({"cwd": str(proj)})
    r = run_dispatch("post-tool", proj, stdin=payload)
    assert r.returncode == 0
    # No record should be appended without a tool name
    trace = proj / ".harness" / "state" / "trace.jsonl"
    if trace.exists():
        assert trace.read_text().strip() == ""
