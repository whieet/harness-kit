"""Smoke tests for the Python core that run on every OS.

These exercise the new implementation directly via subprocess.run([python,
harness_main.py, <dispatch>, ...]) — no bash dependency. The parity tests
(test_parity.py) cover bash-driven behavior on macOS/Linux only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project, run_dispatch


def test_imports_clean():
    """All hook + command modules import without error."""
    code = (
        "import sys; sys.path.insert(0, 'scripts');"
        "from harness import cli;"
        "all_ = {};"
        "all_.update(cli.HOOKS); all_.update(cli.COMMANDS);"
        "[__import__(mod) for mod, _ in all_.values()]"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr


def test_help_when_no_args():
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "harness_main.py")],
        capture_output=True,
        text=True,
        check=False, encoding="utf-8", errors="replace")
    assert r.returncode == 2
    assert "Known hooks" in r.stderr
    assert "session-start" in r.stderr


def test_inert_uninitialized(tmp_path):
    proj = make_project(tmp_path, with_config=False)
    payload = json.dumps({"cwd": str(proj)})
    for ev in (
        "session-start",
        "pre-edit",
        "post-edit",
        "user-prompt",
        "pre-compact",
        "post-tool",
        "tool-failure",
        "plan-approved",
    ):
        r = run_dispatch(ev, proj, stdin=payload)
        assert r.returncode == 0, f"{ev}: rc={r.returncode}\n{r.stderr}"
        assert r.stdout.strip() == "", f"{ev}: should be silent, got {r.stdout!r}"


def test_session_start_emits_json(tmp_path):
    proj = make_project(tmp_path)
    r = run_dispatch("session-start", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "=== Session Handoff (harness-kit) ===" in ctx
    assert "Git: branch=" in ctx
    assert "Active plans" in ctx


def test_pre_edit_scaffolds(tmp_path):
    proj = make_project(tmp_path, extra_config={"plan": {"codeGlob": r"\.py$"}})
    (proj / "src").mkdir()
    target = proj / "src" / "thing.py"
    target.write_text("a = 1\n", encoding="utf-8")
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target)},
    })
    r = run_dispatch("pre-edit", proj, stdin=payload)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert "auto-" in out["hookSpecificOutput"]["additionalContext"]
    plans = list((proj / "docs" / "plans" / "active").glob("auto-*.md"))
    assert len(plans) == 1
    body = plans[0].read_text(encoding="utf-8")
    assert "src/thing.py" in body
    assert "Definition of Done" in body


def test_pre_edit_respects_existing_plan(tmp_path):
    proj = make_project(tmp_path, extra_config={"plan": {"codeGlob": r"\.py$"}})
    (proj / "src").mkdir()
    target = proj / "src" / "thing.py"
    target.write_text("a = 1\n", encoding="utf-8")
    (proj / "docs" / "plans" / "active" / "exists.md").write_text(
        "# exists\nrefers to src/thing.py\n", encoding="utf-8")
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target)},
    })
    r = run_dispatch("pre-edit", proj, stdin=payload)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    # no new auto-* scaffold
    assert not list((proj / "docs" / "plans" / "active").glob("auto-*.md"))


def test_post_edit_loop_trigger(tmp_path):
    proj = make_project(
        tmp_path,
        extra_config={"plan": {"codeGlob": r"\.py$"}, "loopDetection": {"threshold": 2}},
    )
    f = proj / "loopy.py"
    f.write_text("a = 0\n", encoding="utf-8")
    triggered = False
    for i in range(3):
        f.write_text(f"a = {i + 1}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(proj), "add", "loopy.py"], check=True)
        payload = json.dumps({
            "cwd": str(proj),
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(f)},
        })
        r = run_dispatch("post-edit", proj, stdin=payload)
        if "Loop detection" in r.stderr:
            triggered = True
            assert r.returncode == 2
    assert triggered


def test_user_prompt_recovery(tmp_path):
    proj = make_project(tmp_path)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "pre-compact-snapshot.json").write_text(json.dumps({
        "ts": "2025-01-01T00:00:00Z",
        "plans": [{"name": "foo.md", "checked": 1, "total": 3}],
        "lastGateResult": "failed",
        "recentFailedGates": ["tsc"],
    }), encoding="utf-8")
    (state / "pre-compact.dirty").write_text("", encoding="utf-8")
    r = run_dispatch("user-prompt", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0
    out = json.loads(r.stdout.strip())
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "Harness state carried across compaction" in out["hookSpecificOutput"]["additionalContext"]
    assert "tsc" in out["hookSpecificOutput"]["additionalContext"]
    assert not (state / "pre-compact.dirty").exists()


def test_pre_compact_snapshot(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs" / "plans" / "active" / "p1.md").write_text(
        "# p1\n- [x] step a\n- [ ] step b\n", encoding="utf-8")
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "trace.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "session_end", "result": "advisory_fail"}) + "\n")
        fh.write(json.dumps({"event": "gate", "name": "tsc", "ok": False}) + "\n")
    r = run_dispatch("pre-compact", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0, r.stderr
    snap = json.loads((state / "pre-compact-snapshot.json").read_text(encoding="utf-8"))
    assert snap["plans"] == [{"name": "p1.md", "checked": 1, "total": 2}]
    assert snap["lastGateResult"] == "advisory_fail"
    assert snap["recentFailedGates"] == ["tsc"]
    assert (state / "pre-compact.dirty").exists()


def test_post_tool_trace_write(tmp_path):
    proj = make_project(tmp_path)
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "file_path": "/etc/hosts"},
    })
    r = run_dispatch("post-tool", proj, stdin=payload)
    assert r.returncode == 0
    lines = (proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["event"] == "tool_call"
    assert rec["tool"] == "Bash"
    assert rec["file"] == "/etc/hosts"


def test_tool_failure_trace_write(tmp_path):
    proj = make_project(tmp_path)
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "Bash",
        "exit_code": 17,
        "error_message": "boom",
    })
    r = run_dispatch("tool-failure", proj, stdin=payload)
    assert r.returncode == 0
    rec = json.loads((proj / ".harness" / "state" / "trace.jsonl").read_text(encoding="utf-8").strip())
    assert rec["event"] == "tool_fail"
    assert rec["exit_code"] == 17


def test_plan_approved_writes_file(tmp_path):
    proj = make_project(tmp_path)
    plan = "# Adopt Foo\n\nAdopt the Foo framework.\n"
    payload = json.dumps({
        "cwd": str(proj),
        "tool_name": "ExitPlanMode",
        "tool_input": {"plan": plan},
    })
    r = run_dispatch("plan-approved", proj, stdin=payload)
    assert r.returncode == 0
    files = [
        p for p in (proj / "docs" / "plans" / "active").iterdir()
        if p.suffix == ".md" and p.name != ".gitkeep"
    ]
    assert len(files) == 1
    assert "adopt-foo" in files[0].name
    assert "# Adopt Foo" in files[0].read_text(encoding="utf-8")


def test_verify_no_gates(tmp_path):
    proj = make_project(tmp_path)
    r = run_dispatch("harness-verify", proj)
    assert r.returncode == 0
    assert "no gates" in r.stdout.lower()


def test_verify_passing_and_failing_gates(tmp_path):
    proj = make_project(
        tmp_path,
        extra_config={
            "gates": [
                {"name": "ok-gate", "command": "true", "blocking": True},
                {"name": "fail-gate", "command": "echo nope; exit 1", "blocking": True},
            ]
        },
    )
    r = run_dispatch("harness-verify", proj)
    assert r.returncode == 1
    assert "[ok]   ok-gate" in r.stdout
    assert "[FAIL] fail-gate" in r.stdout
    assert "nope" in r.stdout


def test_advisor_dashboard(tmp_path):
    proj = make_project(tmp_path)
    r = run_dispatch("harness-advisor", proj)
    assert r.returncode == 0
    assert "=== Harness dashboard ===" in r.stdout


def test_check_plan_dod_flags_archive_needed(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs" / "plans" / "active" / "done.md").write_text(
        "# done\n- **status**: active\n- [x] one\n- [x] two\n", encoding="utf-8")
    r = run_dispatch("harness-check-plan-dod", proj)
    assert r.returncode == 1
    assert "done.md" in r.stdout
    assert "Move it to completed/" in r.stdout


def test_check_layering_violation(tmp_path):
    proj = make_project(
        tmp_path,
        extra_config={
            "layeringRules": [
                {
                    "scope": "src/ui/**/*.py",
                    "forbidden": r"import db",
                    "message": "UI must not import db",
                }
            ]
        },
    )
    ui = proj / "src" / "ui"
    ui.mkdir(parents=True)
    (ui / "w.py").write_text("import db\n", encoding="utf-8")
    r = run_dispatch("harness-check-layering", proj)
    assert r.returncode == 1
    assert "UI must not import db" in r.stdout
    assert "w.py" in r.stdout


def test_doc_links_dead(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs").mkdir(exist_ok=True)
    (proj / "docs" / "a.md").write_text("see [m](missing.md)\n", encoding="utf-8")
    r = run_dispatch("harness-doc-links", proj)
    assert r.returncode == 1
    assert "missing.md" in r.stderr
    assert "dead link" in r.stderr


def test_doc_links_live(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs").mkdir(exist_ok=True)
    (proj / "docs" / "a.md").write_text("see [b](b.md)\n", encoding="utf-8")
    (proj / "docs" / "b.md").write_text("hi\n", encoding="utf-8")
    r = run_dispatch("harness-doc-links", proj)
    assert r.returncode == 0
    assert "doc links OK" in r.stdout


def test_trace_analyze_json(tmp_path):
    proj = make_project(tmp_path)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "trace.jsonl", "w", encoding="utf-8") as fh:
        for ev in (
            {"event": "session_start"},
            {"event": "tool_call", "tool": "Edit"},
            {"event": "tool_call", "tool": "Edit"},
            {"event": "tool_call", "tool": "Edit"},
            {"event": "session_end", "result": "passed"},
        ):
            fh.write(json.dumps(ev) + "\n")
    r = run_dispatch("harness-trace-analyze", proj, extra_args=["--json"])
    assert r.returncode == 0
    j = json.loads(r.stdout)
    assert j["sessions_started"] == 1
    assert j["gate_passed"] == 1
    assert j["repeated_tools"] == ["Edit"]


def test_maintenance_migrates_legacy_phases(tmp_path):
    proj = make_project(tmp_path)
    cfg_path = proj / ".harness" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["phases"] = [{"name": "old"}]
    cfg.pop("enabledCapabilities", None)
    cfg.pop("effortRouting", None)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    r = run_dispatch("harness-maintenance", proj)
    assert r.returncode == 0
    new_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "phases" not in new_cfg
    assert "enabledCapabilities" in new_cfg
    assert "effortRouting" in new_cfg


def test_init_custom(tmp_path):
    proj_root = tmp_path / "fresh"
    proj_root.mkdir()
    proj = proj_root / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "harness_main.py"), "harness-init", "custom"],
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=env,
        check=False, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    assert (proj / ".harness" / "config.json").exists()
    assert (proj / "docs" / "plans" / "active" / ".gitkeep").exists()
    assert (proj / ".harness" / "hooks" / "pre-commit").exists()
    assert (proj / "CLAUDE.md").exists()


def _fresh_proj(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    return proj


def test_init_writes_claude_md(tmp_path):
    proj = _fresh_proj(tmp_path)
    r = run_dispatch("harness-init", proj, extra_args=["custom"])
    assert r.returncode == 0, r.stderr
    assert "wrote CLAUDE.md" in r.stdout
    body = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/plans" in body  # {{PLAN_DIR}} substituted from the custom preset
    assert "harness-kit:claude-md" in body  # version marker
    assert "{{" not in body  # no leftover placeholders
    assert len(body.splitlines()) <= 120  # fits even the strictest (godot) budget


def test_init_keeps_existing_claude_md(tmp_path):
    proj = _fresh_proj(tmp_path)
    (proj / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
    for args in (["custom"], ["custom", "--force"]):
        r = run_dispatch("harness-init", proj, extra_args=args)
        assert r.returncode == 0, r.stderr
        assert "CLAUDE.md exists — keeping" in r.stdout
        assert (proj / "CLAUDE.md").read_text(encoding="utf-8") == "# mine\n"


def test_init_no_claude_md_flag(tmp_path):
    proj = _fresh_proj(tmp_path)
    r = run_dispatch("harness-init", proj, extra_args=["custom", "--no-claude-md"])
    assert r.returncode == 0, r.stderr
    assert "CLAUDE.md skipped" in r.stdout
    assert not (proj / "CLAUDE.md").exists()


def test_init_lang_zh(tmp_path):
    proj = _fresh_proj(tmp_path)
    r = run_dispatch("harness-init", proj, extra_args=["custom", "--lang", "zh"])
    assert r.returncode == 0, r.stderr
    body = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert "项目章程" in body
    assert "harness-kit:claude-md" in body
    assert "{{" not in body


def test_init_lang_invalid(tmp_path):
    proj = _fresh_proj(tmp_path)
    r = run_dispatch("harness-init", proj, extra_args=["custom", "--lang", "fr"])
    assert r.returncode == 2
    assert "unsupported --lang" in r.stdout


def test_init_respects_dot_claude_dir(tmp_path):
    proj = _fresh_proj(tmp_path)
    (proj / ".claude").mkdir()
    (proj / ".claude" / "CLAUDE.md").write_text("# nested\n", encoding="utf-8")
    r = run_dispatch("harness-init", proj, extra_args=["custom"])
    assert r.returncode == 0, r.stderr
    assert "CLAUDE.md exists — keeping" in r.stdout
    assert not (proj / "CLAUDE.md").exists()


def test_init_imports_agents_md(tmp_path):
    proj = _fresh_proj(tmp_path)
    (proj / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    r = run_dispatch("harness-init", proj, extra_args=["custom"])
    assert r.returncode == 0, r.stderr
    body = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert body.splitlines()[0] == "@AGENTS.md"


def test_init_godot_claude_md_gate_passes(tmp_path):
    """claude-md-budget must pass on a fresh godot project — with the scaffolded
    CLAUDE.md, and (regression: missing-file tolerance) without one."""
    for extra in ([], ["--no-claude-md"]):
        proj = _fresh_proj(tmp_path / ("with" if not extra else "without"))
        (proj / "project.godot").write_text("[application]\n", encoding="utf-8")
        r = run_dispatch("harness-init", proj, extra_args=["godot"] + extra)
        assert r.returncode == 0, r.stderr
        v = run_dispatch("harness-verify", proj)
        assert "[ok]   claude-md-budget" in v.stdout, v.stdout
        assert "[FAIL] claude-md-budget" not in v.stdout


# --- pure unit tests on small Python helpers ---------------------------------


def test_indent_helper():
    from harness.util import indent

    assert indent("") == ""
    assert indent("a\nb") == "  a\n  b"
    assert indent("x", "> ") == "> x"


def test_iso_utc_format():
    from harness.util import iso_utc

    s = iso_utc()
    assert len(s) == 20
    assert s.endswith("Z")
    assert s[10] == "T"


def test_cfg_get_dotted(tmp_path):
    from harness.context import load_context

    proj = make_project(tmp_path, extra_config={
        "deep": {"a": {"b": 7}, "s": "yes", "lst": [1, 2]}
    })
    os.environ["HARNESS_PROJECT_DIR"] = str(proj)
    try:
        ctx = load_context("")
        assert ctx.cfg_get("deep.a.b") == 7
        assert ctx.cfg_get_str("deep.s", "?") == "yes"
        assert ctx.cfg_get("deep.missing", "fallback") == "fallback"
        assert ctx.cfg_get_str("deep.lst") == "[1, 2]"
    finally:
        os.environ.pop("HARNESS_PROJECT_DIR", None)


def test_cap_enabled_defaults(tmp_path):
    from harness.context import load_context

    proj = make_project(tmp_path)
    os.environ["HARNESS_PROJECT_DIR"] = str(proj)
    try:
        ctx = load_context("")
        # Stable: default ON when absent.
        ctx.config.pop("enabledCapabilities", None)
        assert ctx.cap_enabled("planGate") is True
        # Experimental: default OFF.
        assert ctx.cap_enabled("evaluatorAutoDispatch") is False
        # Explicit overrides
        ctx.config["enabledCapabilities"] = {"planGate": False, "evaluatorAutoDispatch": True}
        assert ctx.cap_enabled("planGate") is False
        assert ctx.cap_enabled("evaluatorAutoDispatch") is True
    finally:
        os.environ.pop("HARNESS_PROJECT_DIR", None)
