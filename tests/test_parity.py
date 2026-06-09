"""Parity tests — for each hook/command, run the OLD bash and the NEW Python
implementation against an identical fixture, normalize obvious volatile bits
(timestamps, abs paths, random plan slugs that embed the date), and assert the
outputs match.

Skipped on Windows: the OLD bash scripts use Unix-only utilities (realpath,
mktemp, pgrep), so the old impl can only run on macOS/Linux/Git-Bash. The new
impl is exercised by tests/test_smoke.py on every platform.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="old bash impl needs Unix tools"
)


# --- normalization -----------------------------------------------------------

ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PLAN_AUTO_RE = re.compile(r"auto-\d{4}-\d{2}-\d{2}-\d{6}-")
MIN_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def _norm(text: str, *, proj: Path | None = None) -> str:
    if proj:
        text = text.replace(str(proj), "<PROJ>")
        text = text.replace(str(proj.resolve()), "<PROJ>")
    text = ISO_TS_RE.sub("<ISO_TS>", text)
    text = MIN_TS_RE.sub("<MIN_TS>", text)
    text = PLAN_AUTO_RE.sub("auto-<TS>-", text)
    text = DATE_RE.sub("<DATE>", text)
    return text.strip()


# --- runners -----------------------------------------------------------------

def _run_old_hook(old: Path, script: str, proj: Path, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(old / "scripts" / script)],
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj)},
        check=False,
    )


def _run_old_bin(old: Path, name: str, proj: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(old / "bin" / name), *(args or [])],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj)},
        check=False,
    )


def _run_new_hook(dispatch: str, proj: Path, stdin: str = "") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "run-hook"), dispatch],
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _run_new_bin(name: str, proj: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    return subprocess.run(
        ["bash", str(REPO_ROOT / "bin" / name), *(args or [])],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# --- the fixtures ------------------------------------------------------------


@pytest.fixture
def proj_uninit(tmp_path):
    return make_project(tmp_path, with_config=False)


@pytest.fixture
def proj_basic(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def proj_with_metrics(tmp_path):
    p = make_project(
        tmp_path,
        extra_config={
            "metrics": [
                {"name": "plans", "glob": "docs/plans/**/*.md", "exclude": "gitkeep"},
            ],
        },
    )
    return p


# --- tests: hooks ------------------------------------------------------------


def _payload(cwd: Path, **extra) -> str:
    base = {"cwd": str(cwd), "session_id": "test-session"}
    base.update(extra)
    return json.dumps(base)


def test_inert_when_uninitialized(old_plugin_root, proj_uninit):
    """All hooks must exit 0 with no output when .harness/config.json is absent."""
    for script, dispatch in [
        ("on-session-start.sh", "session-start"),
        ("on-pre-edit.sh", "pre-edit"),
        ("on-post-edit.sh", "post-edit"),
        ("on-user-prompt.sh", "user-prompt"),
        ("on-pre-compact.sh", "pre-compact"),
        ("on-post-tool.sh", "post-tool"),
        ("on-tool-failure.sh", "tool-failure"),
        ("on-plan-approved.sh", "plan-approved"),
    ]:
        old = _run_old_hook(old_plugin_root, script, proj_uninit, _payload(proj_uninit))
        new = _run_new_hook(dispatch, proj_uninit, _payload(proj_uninit))
        assert old.returncode == 0, f"{script} old: rc={old.returncode} stderr={old.stderr}"
        assert new.returncode == 0, f"{dispatch} new: rc={new.returncode} stderr={new.stderr}"
        assert old.stdout.strip() == "", f"{script} should be silent when uninit; got: {old.stdout!r}"
        assert new.stdout.strip() == "", f"{dispatch} should be silent when uninit; got: {new.stdout!r}"


def test_session_start_emits_handoff(old_plugin_root, proj_basic):
    payload = _payload(proj_basic)
    old = _run_old_hook(old_plugin_root, "on-session-start.sh", proj_basic, payload)
    new = _run_new_hook("session-start", proj_basic, payload)
    assert old.returncode == 0
    assert new.returncode == 0
    # Both should produce a JSON hookSpecificOutput
    o = json.loads(old.stdout.strip())
    n = json.loads(new.stdout.strip())
    assert o["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert n["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    o_ctx = _norm(o["hookSpecificOutput"]["additionalContext"], proj=proj_basic)
    n_ctx = _norm(n["hookSpecificOutput"]["additionalContext"], proj=proj_basic)
    # Tolerate minor wording / ordering differences by asserting key landmarks.
    for marker in ("=== Session Handoff (harness-kit) ===", "Git: branch=", "Active plans"):
        assert marker in o_ctx
        assert marker in n_ctx


def test_pre_edit_scaffolds_plan_when_uncovered(old_plugin_root, tmp_path):
    """File matches codeGlob but no plan covers it → both impls should auto-scaffold
    a plan file and emit additionalContext."""

    # Each impl runs against its OWN project so they don't see each other's scaffolds.
    proj_old = make_project(tmp_path / "old", extra_config={"plan": {"codeGlob": r"\.py$"}})
    proj_new = make_project(tmp_path / "new", extra_config={"plan": {"codeGlob": r"\.py$"}})
    # Move the project dirs to share tmp_path.
    # (make_project already created them under tmp_path/old/proj and tmp_path/new/proj.)
    (proj_old / "src").mkdir()
    (proj_new / "src").mkdir()
    (proj_old / "src" / "thing.py").write_text("x = 1\n")
    (proj_new / "src" / "thing.py").write_text("x = 1\n")

    payload_old = _payload(proj_old, tool_name="Edit", tool_input={"file_path": str(proj_old / "src" / "thing.py")})
    payload_new = _payload(proj_new, tool_name="Edit", tool_input={"file_path": str(proj_new / "src" / "thing.py")})

    old = _run_old_hook(old_plugin_root, "on-pre-edit.sh", proj_old, payload_old)
    new = _run_new_hook("pre-edit", proj_new, payload_new)
    assert old.returncode == 0, old.stderr
    assert new.returncode == 0, new.stderr

    old_plans = list((proj_old / "docs" / "plans" / "active").glob("auto-*.md"))
    new_plans = list((proj_new / "docs" / "plans" / "active").glob("auto-*.md"))
    assert len(old_plans) == 1, f"old should scaffold one plan, got {old_plans}"
    assert len(new_plans) == 1, f"new should scaffold one plan, got {new_plans}"
    # Slugs should agree (both based on src/thing.py)
    old_slug = re.sub(r"^auto-\d{4}-\d{2}-\d{2}-\d{6}-", "", old_plans[0].name)
    new_slug = re.sub(r"^auto-\d{4}-\d{2}-\d{2}-\d{6}-", "", new_plans[0].name)
    assert old_slug == new_slug == "src-thing.md"

    # Plan bodies should be essentially the same after normalization.
    assert _norm(old_plans[0].read_text(), proj=proj_old) == _norm(new_plans[0].read_text(), proj=proj_new)


def test_pre_edit_skips_when_plan_covers_file(old_plugin_root, tmp_path):
    """If an active plan already mentions the file, no new scaffold."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config={"plan": {"codeGlob": r"\.py$"}})
        (proj / "src").mkdir()
        target = proj / "src" / "thing.py"
        target.write_text("x = 1\n")
        # Pre-existing plan that references the file path:
        (proj / "docs" / "plans" / "active" / "existing.md").write_text(
            "# existing\nthis touches src/thing.py\n"
        )
        payload = _payload(proj, tool_name="Edit", tool_input={"file_path": str(target)})
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-pre-edit.sh", proj, payload)
        else:
            r = _run_new_hook("pre-edit", proj, payload)
        assert r.returncode == 0
        assert r.stdout.strip() == "", f"{label}: should emit nothing; got {r.stdout!r}"
        # No new auto-* file was created
        assert not list((proj / "docs" / "plans" / "active").glob("auto-*.md"))


def test_post_edit_loop_threshold(old_plugin_root, tmp_path):
    """After threshold reached, both emit a nudge to stderr and exit 2."""
    for label in ("old", "new"):
        proj = make_project(
            tmp_path / label,
            extra_config={
                "plan": {"codeGlob": r"\.py$"},
                "loopDetection": {"threshold": 2},
            },
        )
        f = proj / "loopy.py"
        f.write_text("a = 1\n")
        # Simulate edits by writing different contents AND staging so git diff --numstat reports.
        edits_seen = 0
        for i in range(3):
            f.write_text(f"a = {i}\n")
            subprocess.run(["git", "-C", str(proj), "add", "loopy.py"], check=True)
            payload = _payload(proj, tool_name="Edit", tool_input={"file_path": str(f)})
            if label == "old":
                r = _run_old_hook(old_plugin_root, "on-post-edit.sh", proj, payload)
            else:
                r = _run_new_hook("post-edit", proj, payload)
            if "Loop detection" in r.stderr:
                edits_seen += 1
        assert edits_seen >= 1, f"{label} never fired the loop warning over 3 edits; stderr={r.stderr!r}"


def test_user_prompt_no_dirty_marker(old_plugin_root, proj_basic):
    """Without a dirty marker, both must emit nothing."""
    payload = _payload(proj_basic)
    old = _run_old_hook(old_plugin_root, "on-user-prompt.sh", proj_basic, payload)
    new = _run_new_hook("user-prompt", proj_basic, payload)
    assert old.returncode == 0 and old.stdout.strip() == ""
    assert new.returncode == 0 and new.stdout.strip() == ""


def test_user_prompt_with_snapshot(old_plugin_root, tmp_path):
    """With a snapshot + dirty marker, both should emit additionalContext and clear the marker."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        state = proj / ".harness" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "pre-compact-snapshot.json").write_text(json.dumps({
            "ts": "2025-01-01T00:00:00Z",
            "plans": [{"name": "foo.md", "checked": 1, "total": 3}],
            "lastGateResult": "failed",
            "recentFailedGates": ["typecheck", "eslint"],
        }))
        (state / "pre-compact.dirty").write_text("")
        payload = _payload(proj)
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-user-prompt.sh", proj, payload)
        else:
            r = _run_new_hook("user-prompt", proj, payload)
        assert r.returncode == 0
        out = json.loads(r.stdout.strip())
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Harness state carried across compaction" in ctx
        assert "active plan foo.md: 1/3" in ctx
        assert "last completion gate: failed" in ctx
        assert "typecheck" in ctx and "eslint" in ctx
        assert not (state / "pre-compact.dirty").exists(), f"{label} should have cleared dirty marker"


def test_pre_compact_writes_snapshot(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        # Plant an active plan with partial DoD.
        (proj / "docs" / "plans" / "active" / "p1.md").write_text(
            "# p1\n- [x] step a\n- [ ] step b\n- [ ] step c\n"
        )
        # Plant a trace with a session_end and a failing gate.
        state = proj / ".harness" / "state"
        state.mkdir(parents=True, exist_ok=True)
        with open(state / "trace.jsonl", "w") as f:
            f.write(json.dumps({"ts": "2025-01-01T00:00:00Z", "event": "session_end", "result": "failed"}) + "\n")
            f.write(json.dumps({"ts": "2025-01-01T00:00:00Z", "event": "gate", "name": "eslint", "ok": False}) + "\n")
        payload = _payload(proj)
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-pre-compact.sh", proj, payload)
        else:
            r = _run_new_hook("pre-compact", proj, payload)
        assert r.returncode == 0, r.stderr
        snap = json.loads((state / "pre-compact-snapshot.json").read_text())
        assert snap["plans"] == [{"name": "p1.md", "checked": 1, "total": 3}]
        assert snap["lastGateResult"] == "failed"
        assert snap["recentFailedGates"] == ["eslint"]
        assert (state / "pre-compact.dirty").exists()


def test_post_tool_appends_trace(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        payload = _payload(proj, tool_name="Bash", tool_input={"command": "ls"})
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-post-tool.sh", proj, payload)
        else:
            r = _run_new_hook("post-tool", proj, payload)
        assert r.returncode == 0
        trace = (proj / ".harness" / "state" / "trace.jsonl").read_text()
        rec = json.loads(trace.strip().splitlines()[-1])
        assert rec["event"] == "tool_call"
        assert rec["tool"] == "Bash"


def test_tool_failure_appends_trace(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        payload = _payload(proj, tool_name="Bash", exit_code=2, error_message="oops")
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-tool-failure.sh", proj, payload)
        else:
            r = _run_new_hook("tool-failure", proj, payload)
        assert r.returncode == 0
        trace = (proj / ".harness" / "state" / "trace.jsonl").read_text()
        rec = json.loads(trace.strip().splitlines()[-1])
        assert rec["event"] == "tool_fail"
        assert rec["tool"] == "Bash"
        assert rec["exit_code"] == 2
        assert rec["error_message"] == "oops"


def test_plan_approved_persists_plan(old_plugin_root, tmp_path):
    plan_md = "# My Plan\n\nDo a thing.\n"
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        payload = _payload(proj, tool_name="ExitPlanMode", tool_input={"plan": plan_md})
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-plan-approved.sh", proj, payload)
        else:
            r = _run_new_hook("plan-approved", proj, payload)
        assert r.returncode == 0
        files = list((proj / "docs" / "plans" / "active").glob("*.md"))
        files = [f for f in files if f.name != ".gitkeep"]
        assert len(files) == 1, f"{label}: expected one file, got {files}"
        body = files[0].read_text()
        assert "# My Plan" in body
        assert "Definition of Done" in body
        assert "harness-verify" in body


# --- tests: bin commands -----------------------------------------------------


def test_verify_no_gates_is_clean(old_plugin_root, proj_basic):
    """With gates=[] both implementations should print the no-gates message and exit 0."""
    old = _run_old_bin(old_plugin_root, "harness-verify", proj_basic)
    new = _run_new_bin("harness-verify", proj_basic)
    assert old.returncode == 0
    assert new.returncode == 0
    assert "no gates" in old.stdout.lower()
    assert "no gates" in new.stdout.lower()


def test_verify_runs_passing_and_failing_gate(old_plugin_root, tmp_path):
    extra = {
        "gates": [
            {"name": "ok-gate", "command": "true", "blocking": True},
            {"name": "fail-gate", "command": "echo nope && exit 1", "blocking": True},
        ]
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-verify", proj)
        else:
            r = _run_new_bin("harness-verify", proj)
        assert r.returncode == 1, f"{label}: expected FAIL exit; got rc={r.returncode}\n{r.stdout}\n{r.stderr}"
        assert "[ok]   ok-gate" in r.stdout
        assert "[FAIL] fail-gate" in r.stdout
        assert "FAILED" in r.stdout


def test_verify_non_blocking_gate_warns_but_passes(old_plugin_root, tmp_path):
    extra = {
        "gates": [
            {"name": "soft-bad", "command": "exit 1", "blocking": False},
        ]
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-verify", proj)
        else:
            r = _run_new_bin("harness-verify", proj)
        assert r.returncode == 0, f"{label}: soft fail should not block; got rc={r.returncode}"
        assert "[warn] soft-bad" in r.stdout


def test_init_godot(old_plugin_root, tmp_path):
    """harness-init custom — both should scaffold .harness/* and hooks."""
    for label in ("old", "new"):
        proj_root = tmp_path / label
        proj_root.mkdir()
        proj = proj_root / "p"
        proj.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proj)}
        if label == "old":
            cmd = ["bash", str(old_plugin_root / "bin" / "harness-init"), "custom"]
        else:
            cmd = ["bash", str(REPO_ROOT / "bin" / "harness-init"), "custom"]
            env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
        r = subprocess.run(cmd, cwd=str(proj), capture_output=True, text=True, env=env, check=False)
        assert r.returncode == 0, f"{label}: rc={r.returncode}\n{r.stdout}\n{r.stderr}"
        assert (proj / ".harness" / "config.json").exists()
        assert (proj / ".harness" / "hooks" / "pre-commit").exists()
        # plan.dir is configured to docs/plans for the custom preset
        assert (proj / "docs" / "plans" / "active" / ".gitkeep").exists()
        assert (proj / "docs" / "plans" / "completed" / ".gitkeep").exists()
        assert (proj / ".harness" / ".gitignore").read_text().strip() == "state/"


def test_check_plan_dod_flags_uncompleted(old_plugin_root, tmp_path):
    """A plan with status=completed but still in active/ should flag."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "docs" / "plans" / "active" / "stuck.md").write_text(
            "# stuck\n- **status**: completed\n- [x] one\n- [x] two\n"
        )
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-check-plan-dod", proj)
        else:
            r = _run_new_bin("harness-check-plan-dod", proj)
        assert r.returncode == 1, f"{label}: should flag; rc={r.returncode}\n{r.stdout}"
        assert "stuck.md" in r.stdout
        assert "Move it to completed/" in r.stdout


def test_check_layering_no_rules(old_plugin_root, proj_basic):
    old = _run_old_bin(old_plugin_root, "harness-check-layering", proj_basic)
    new = _run_new_bin("harness-check-layering", proj_basic)
    assert old.returncode == new.returncode == 0
    assert "no rules configured" in old.stdout
    assert "no rules configured" in new.stdout


def test_check_layering_violation(old_plugin_root, tmp_path):
    extra = {
        "layeringRules": [
            {"scope": "src/ui/**/*.py", "forbidden": r"import db", "message": "UI must not import db"}
        ]
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        ui = proj / "src" / "ui"
        ui.mkdir(parents=True)
        (ui / "widget.py").write_text("import db\nprint('hi')\n")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-check-layering", proj)
        else:
            r = _run_new_bin("harness-check-layering", proj)
        assert r.returncode == 1, f"{label}: rc={r.returncode}\n{r.stdout}"
        assert "widget.py" in r.stdout
        assert "UI must not import db" in r.stdout


def test_doc_links_dead_link(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "docs").mkdir(exist_ok=True)
        (proj / "docs" / "a.md").write_text("link: [x](missing.md)\n")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-links", proj)
        else:
            r = _run_new_bin("harness-doc-links", proj)
        assert r.returncode == 1, f"{label}: rc={r.returncode}\nout={r.stdout}\nerr={r.stderr}"
        assert "dead link" in r.stderr
        assert "missing.md" in r.stderr


def test_advisor_smoke(old_plugin_root, proj_basic):
    old = _run_old_bin(old_plugin_root, "harness-advisor", proj_basic)
    new = _run_new_bin("harness-advisor", proj_basic)
    assert old.returncode == new.returncode == 0
    for key in ("=== Harness dashboard ===", "Capabilities:"):
        assert key in old.stdout
        assert key in new.stdout


def test_trace_analyze_empty(old_plugin_root, proj_basic):
    old = _run_old_bin(old_plugin_root, "harness-trace-analyze", proj_basic)
    new = _run_new_bin("harness-trace-analyze", proj_basic)
    assert old.returncode == new.returncode == 0
    assert "sessions: started=0" in old.stdout
    assert "sessions: started=0" in new.stdout


def test_trace_analyze_json(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        state = proj / ".harness" / "state"
        state.mkdir(parents=True, exist_ok=True)
        with open(state / "trace.jsonl", "w") as f:
            f.write(json.dumps({"event": "session_start"}) + "\n")
            f.write(json.dumps({"event": "tool_call", "tool": "Edit"}) + "\n")
            f.write(json.dumps({"event": "session_end", "result": "passed"}) + "\n")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-trace-analyze", proj, ["--json"])
        else:
            r = _run_new_bin("harness-trace-analyze", proj, ["--json"])
        assert r.returncode == 0
        j = json.loads(r.stdout)
        assert j["sessions_started"] == 1
        assert j["sessions_ended"] == 1
        assert j["gate_passed"] == 1
        assert j["tool_calls"] == 1


def test_maintenance_migrates_legacy_phases(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        # Inject legacy `phases` (and strip the new keys so migration triggers).
        cfg_path = proj / ".harness" / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["phases"] = [{"name": "old-phase"}]
        cfg.pop("enabledCapabilities", None)
        cfg.pop("effortRouting", None)
        cfg_path.write_text(json.dumps(cfg, indent=2))
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-maintenance", proj)
        else:
            r = _run_new_bin("harness-maintenance", proj)
        assert r.returncode == 0, f"{label}: rc={r.returncode}\n{r.stdout}\n{r.stderr}"
        new_cfg = json.loads(cfg_path.read_text())
        assert "phases" not in new_cfg
        assert "enabledCapabilities" in new_cfg
        assert "effortRouting" in new_cfg
