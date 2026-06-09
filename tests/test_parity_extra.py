"""Extra parity tests for the two dispatches the initial suite missed:
stop-verify (the Stop hook / "Ralph Loop" gate) and harness-doc-gardening
(the 161-line drift scanner). Plus narrow regression tests for the
behavioral parity fixes (pgrep, multi-link-per-line, plan strip,
advisor empty, init stream, trace compact JSON)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="old bash impl needs Unix tools"
)


def _run_old_hook(old: Path, script: str, proj: Path, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(old / "scripts" / script)],
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj)},
        check=False, encoding="utf-8", errors="replace")


def _run_old_bin(old: Path, name: str, proj: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(old / "bin" / name), *(args or [])],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj)},
        check=False, encoding="utf-8", errors="replace")


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
        check=False, encoding="utf-8", errors="replace")


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
        check=False, encoding="utf-8", errors="replace")


def _payload(cwd: Path, **extra) -> str:
    base = {"cwd": str(cwd), "session_id": "test-session"}
    base.update(extra)
    return json.dumps(base)


# -------------------------------------------------------------- stop-verify ---


def test_stop_verify_clean_project(old_plugin_root, tmp_path):
    """No gates, no plans, clean tree → both pass and exit 0 with the same
    pre-completion-gate banner."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 0, f"{label}: rc={r.returncode}\n{r.stderr}"
        # Both impls route ALL output to stderr (exec >&2 in bash,
        # sys.stderr.write in python).
        assert "=== harness-kit: pre-completion gate ===" in r.stderr
        assert "[1/3] harness-verify" in r.stderr
        assert "[2/3] uncommitted changes" in r.stderr
        assert "[3/3] active-plan DoD" in r.stderr
        assert "(no active plans)" in r.stderr
        assert "✅ pre-completion gate passed" in r.stderr
        assert "working tree clean" in r.stderr


def test_stop_verify_failing_gate_blocks_in_strict(old_plugin_root, tmp_path):
    """A failing gate + verificationMode=strict → exit 2 (blocks Claude)."""
    extra = {
        "gates": [{"name": "bust", "command": "exit 1", "blocking": True}],
        "verificationMode": "strict",
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 2, f"{label}: expected exit 2 (block); got rc={r.returncode}\n{r.stderr}"
        assert "❌" in r.stderr
        assert "fix the above" in r.stderr
        assert "verificationMode=strict" in r.stderr
        # Trace should record a session_end with result=failed
        trace = (proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8")
        last = json.loads(trace.strip().splitlines()[-1])
        assert last["event"] == "session_end"
        assert last["result"] == "failed"


def test_stop_verify_failing_gate_advisory_passes(old_plugin_root, tmp_path):
    """verificationMode=advisory → fail does NOT block; exit 0."""
    extra = {
        "gates": [{"name": "bust", "command": "exit 1", "blocking": True}],
        "verificationMode": "advisory",
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 0, f"{label}: advisory should not block; rc={r.returncode}"
        assert "advisory mode" in r.stderr
        trace = (proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8")
        last = json.loads(trace.strip().splitlines()[-1])
        assert last["result"] == "advisory_fail"


def test_stop_verify_plan_dod_unfinished_blocks(old_plugin_root, tmp_path):
    """An active plan with mixed checked/unchecked items blocks in strict mode."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "docs" / "plans" / "active" / "wip.md").write_text(
            "# wip\n- [x] step a\n- [ ] step b\n- [ ] step c\n", encoding="utf-8")
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 2, f"{label}: rc={r.returncode}\n{r.stderr}"
        assert "wip.md" in r.stderr
        assert "1/3 done, 2 unfinished — blocking" in r.stderr


def test_stop_verify_plan_dod_complete_passes(old_plugin_root, tmp_path):
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "docs" / "plans" / "active" / "done.md").write_text(
            "# done\n- [x] step a\n- [x] step b\n", encoding="utf-8")
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 0, f"{label}: rc={r.returncode}\n{r.stderr}"
        assert "done.md: all 2 done" in r.stderr


def test_stop_verify_uncommitted_advisory(old_plugin_root, tmp_path):
    """Uncommitted changes show the ⚠️ line but do NOT block."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "wip.txt").write_text("wip\n", encoding="utf-8")
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-stop-verify.sh", proj, _payload(proj))
        else:
            r = _run_new_hook("stop-verify", proj, _payload(proj))
        assert r.returncode == 0
        assert "uncommitted work present" in r.stderr


# -------------------------------------------------- harness-doc-gardening ---


def test_doc_gardening_clean(old_plugin_root, proj_basic):
    """No drift configured → both should report 'no drift'."""
    old = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj_basic)
    new = _run_new_bin("harness-doc-gardening", proj_basic)
    assert old.returncode == new.returncode == 0
    assert "doc-gardening: no drift" in old.stdout
    assert "doc-gardening: no drift" in new.stdout


def test_doc_gardening_status_mismatch(old_plugin_root, tmp_path):
    """Plan in completed/ whose status field is NOT 'completed' → flag."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        (proj / "docs" / "plans" / "completed" / "mismatched.md").write_text(
            "# mismatched\n- **status**: active\n", encoding="utf-8")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj)
        else:
            r = _run_new_bin("harness-doc-gardening", proj)
        assert r.returncode == 1, f"{label}: rc={r.returncode}\n{r.stdout}"
        assert "status-mismatch" in r.stdout
        assert "mismatched.md" in r.stdout


def test_doc_gardening_template_field(old_plugin_root, tmp_path):
    """plan.requiredFields → flag completed plans missing any of those fields."""
    extra = {"plan": {"requiredFields": ["status", "Definition of Done"]}}
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        (proj / "docs" / "plans" / "completed" / "missing.md").write_text(
            "# missing\n- **status**: completed\n\nNo DoD here.\n", encoding="utf-8")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj)
        else:
            r = _run_new_bin("harness-doc-gardening", proj)
        assert r.returncode == 1
        assert "template-field" in r.stdout
        assert "Definition of Done" in r.stdout


def test_doc_gardening_placeholder(old_plugin_root, tmp_path):
    """Placeholder strings in docs trigger the placeholder check."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        d = proj / "docs"
        d.mkdir(exist_ok=True)
        (d / "spec.md").write_text("# spec\n\nTODO: fill\n", encoding="utf-8")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj)
        else:
            r = _run_new_bin("harness-doc-gardening", proj)
        assert r.returncode == 1
        assert "placeholder" in r.stdout
        assert "TODO: fill" in r.stdout


def test_doc_gardening_arch_drift_forward(old_plugin_root, tmp_path):
    """architecturePath references a path that doesn't exist on disk → flag."""
    extra = {
        "docs": {
            "architecturePath": "ARCHITECTURE.md",
            "layerPathRegex": r"src/[a-z]+",
        }
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        (proj / "ARCHITECTURE.md").write_text("we declare src/missing and src/present.\n", encoding="utf-8")
        (proj / "src").mkdir()
        (proj / "src" / "present").mkdir()
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj)
        else:
            r = _run_new_bin("harness-doc-gardening", proj)
        assert r.returncode == 1
        assert "arch-drift" in r.stdout
        assert "src/missing" in r.stdout


def test_doc_gardening_naming(old_plugin_root, tmp_path):
    """namingGlob + namingDisallow → flag files violating the convention."""
    extra = {
        "docs": {
            "namingGlob": "src/**/*.py",
            "namingDisallow": "[A-Z]",  # no uppercase in basename
        }
    }
    for label in ("old", "new"):
        proj = make_project(tmp_path / label, extra_config=extra)
        (proj / "src").mkdir()
        (proj / "src" / "BadName.py").write_text("x = 1\n", encoding="utf-8")
        (proj / "src" / "good_name.py").write_text("x = 1\n", encoding="utf-8")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-gardening", proj)
        else:
            r = _run_new_bin("harness-doc-gardening", proj)
        assert r.returncode == 1
        assert "naming" in r.stdout
        assert "BadName.py" in r.stdout
        assert "good_name.py" not in r.stdout


# ----------------------------------------- regression tests for the fixes ---


def test_doc_links_multi_link_line_matches_bash(old_plugin_root, tmp_path):
    """Regression for S2: a line with MANY links → both impls should report
    the SAME dead links (or none, if the last link on the line is live)."""
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        d = proj / "docs"
        d.mkdir(exist_ok=True)
        # Line has TWO bracket-paren constructs; bash's sed catches only the
        # LAST one (live.md, present on disk) → no failure. Python (after the
        # fix) must do the same.
        (d / "links.md").write_text("see [dead](missing.md) and [live](live.md)\n", encoding="utf-8")
        (d / "live.md").write_text("alive\n", encoding="utf-8")
        if label == "old":
            r = _run_old_bin(old_plugin_root, "harness-doc-links", proj)
        else:
            r = _run_new_bin("harness-doc-links", proj)
        assert r.returncode == 0, (
            f"{label}: bash's last-link-only semantics → live.md is the captured "
            f"target → no dead link → rc=0; got rc={r.returncode}\n"
            f"stderr={r.stderr}\nstdout={r.stdout}"
        )


def test_plan_approved_preserves_whitespace(old_plugin_root, tmp_path):
    """Regression for S3: plan body should be saved verbatim (no .strip())."""
    plan = "\n\n# Title with surrounding blanks\n\nbody\n\n"
    for label in ("old", "new"):
        proj = make_project(tmp_path / label)
        payload = _payload(proj, tool_name="ExitPlanMode", tool_input={"plan": plan})
        if label == "old":
            r = _run_old_hook(old_plugin_root, "on-plan-approved.sh", proj, payload)
        else:
            r = _run_new_hook("plan-approved", proj, payload)
        assert r.returncode == 0
        files = [
            p for p in (proj / "docs" / "plans" / "active").iterdir()
            if p.suffix == ".md" and p.name != ".gitkeep"
        ]
        assert len(files) == 1
        body = files[0].read_text(encoding="utf-8")
        # The literal plan (with its leading/trailing blank lines) should
        # appear verbatim inside the saved file body.
        assert plan in body, f"{label}: plan whitespace was rewritten\nbody:\n{body}"


def test_advisor_runs_on_uninitialized_project(old_plugin_root, tmp_path):
    """Regression for S4: bash advisor always printed the dashboard, even
    without .harness/config.json. The Python port now matches."""
    proj_root = tmp_path / "uninit"
    proj_root.mkdir()
    proj = proj_root / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    old = _run_old_bin(old_plugin_root, "harness-advisor", proj)
    new = _run_new_bin("harness-advisor", proj)
    assert old.returncode == 0
    assert new.returncode == 0
    assert "=== Harness dashboard ===" in old.stdout
    assert "=== Harness dashboard ===" in new.stdout
    for txt in ("Capabilities: ",):
        assert txt in old.stdout
        assert txt in new.stdout


def test_init_unknown_arg_goes_to_stdout(old_plugin_root, tmp_path):
    """Regression for M4: error messages go to stdout (bash parity)."""
    proj = make_project(tmp_path, with_config=False)
    for label, runner in (("old", lambda: _run_old_bin(old_plugin_root, "harness-init", proj, ["bogus"])),
                          ("new", lambda: _run_new_bin("harness-init", proj, ["bogus"]))):
        r = runner()
        assert r.returncode == 2
        assert "unknown arg" in r.stdout, f"{label}: stdout should carry the error; stderr={r.stderr!r}"


def test_trace_jsonl_uses_compact_separators(tmp_path):
    """Regression for M1: trace.jsonl should have no spaces around : or , so
    that bash-written and python-written records are byte-comparable."""
    proj = make_project(tmp_path)
    payload = _payload(proj, tool_name="Bash", tool_input={"command": "ls"})
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "run-hook"), "post-tool"],
        cwd=str(proj),
        input=payload,
        capture_output=True,
        text=True,
        env={**os.environ, "HARNESS_KIT_ROOT": str(REPO_ROOT), "CLAUDE_PROJECT_DIR": str(proj)},
        check=False, encoding="utf-8", errors="replace")
    assert r.returncode == 0
    line = (proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8").strip()
    # Compact: no ": " and no ", "
    assert ": " not in line, f"trace line has space after colon: {line!r}"
    assert ", " not in line, f"trace line has space after comma: {line!r}"


def test_pgrep_basename_only(tmp_path, monkeypatch):
    """Regression for S1: process_running should use bare pgrep (process name),
    not pgrep -f (full cmdline). Verified by patching subprocess.run and
    checking the args."""
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from harness import util

    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        class R:
            returncode = 1
            stdout = ""
        return R()

    monkeypatch.setattr("harness.util.subprocess.run", fake_run)
    # Force the Unix branch even if we ever run on Windows-style.
    monkeypatch.setattr("harness.util.platform.system", lambda: "Linux")
    util.process_running("godot")
    assert captured["args"] == ["pgrep", "godot"], (
        f"Expected `pgrep godot` (no -f); got {captured['args']!r}"
    )


# Shared fixtures expected from test_parity.py — duplicate the minimal ones
# we need here so this module can run standalone.

@pytest.fixture
def proj_basic(tmp_path):
    return make_project(tmp_path)
