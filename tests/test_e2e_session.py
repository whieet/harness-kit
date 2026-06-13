"""Deterministic full-session replay e2e.

Each scenario replays a realistic Claude Code session as the hook-event
sequence the harness would actually receive (session-start → edits →
pre-compact → user-prompt → stop-verify), against one scaffolded project, and
asserts the cross-hook state evolution: plan files, loop counters, snapshots,
and the trace timeline. No model calls — this is the free middle layer of the
test pyramid (docs/testing.md); the live layer (test_live_e2e.py) replays the
same disciplines through a real headless Claude.

Scenario ↔ discipline map (IDs referenced by tests/e2e_workflow_rubric.md):
  S1 plan-gating lifecycle    S2 loop detection → analyzer
  S3 verification gate modes  S4 context survival (compact → resume)
  S5 trace completeness       S6 init → verify green path
  S7 evaluator recipe + effort routing
"""
from __future__ import annotations

import json
import subprocess

from tests._helpers import edit_payload, make_project, read_trace, run_dispatch


def _events(proj, *names):
    return [r for r in read_trace(proj) if r.get("event") in names]


def test_s1_plan_gate_lifecycle(tmp_path):
    proj = make_project(tmp_path, extra_config={"plan": {"codeGlob": r"\.py$"}})
    assert run_dispatch("session-start", proj, stdin=json.dumps({"cwd": str(proj)})).returncode == 0

    (proj / "src").mkdir()
    target = proj / "src" / "x.py"
    target.write_text("a = 1\n", encoding="utf-8")
    r = run_dispatch("pre-edit", proj, stdin=edit_payload(proj, target))
    assert r.returncode == 0
    plans = list((proj / "docs" / "plans" / "active").glob("auto-*.md"))
    assert len(plans) == 1, "plan gate must scaffold a covering plan before the edit"
    body = plans[0].read_text(encoding="utf-8")
    assert "src/x.py" in body and "Definition of Done" in body

    assert run_dispatch("post-tool", proj, stdin=edit_payload(proj, target)).returncode == 0

    # Partially-done plan (some checked, some not) must block a strict finish.
    plans[0].write_text(body.replace("- [ ]", "- [x]", 1), encoding="utf-8")
    r = run_dispatch("stop-verify", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 2
    assert "blocking" in r.stderr and "pre-completion gate failed" in r.stderr

    # All boxes ticked → the same gate now lets the session finish.
    done = plans[0].read_text(encoding="utf-8").replace("- [ ]", "- [x]")
    plans[0].write_text(done, encoding="utf-8")
    r = run_dispatch("stop-verify", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0, r.stderr
    assert "pre-completion gate passed" in r.stderr

    # The trace tells the same story, in order.
    timeline = [(r["event"], r.get("result")) for r in _events(
        proj, "session_start", "tool_call", "session_end")]
    assert timeline == [
        ("session_start", None),
        ("tool_call", None),
        ("session_end", "failed"),
        ("session_end", "passed"),
    ]


def test_s2_loop_detect_feeds_analyzer(tmp_path):
    proj = make_project(
        tmp_path,
        extra_config={"plan": {"codeGlob": r"\.py$"}, "loopDetection": {"threshold": 2}},
    )
    f = proj / "loopy.py"
    f.write_text("a = 0\n", encoding="utf-8")
    warned = False
    for i in range(5):
        f.write_text(f"a = {i + 1}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(proj), "add", "loopy.py"], check=True)
        r = run_dispatch("post-edit", proj, stdin=edit_payload(proj, f))
        if "Loop detection" in r.stderr:
            warned = True
            assert r.returncode == 2
    assert warned, "threshold=2 must warn within 5 edits of the same file"

    counts = json.loads((proj / ".harness" / "state" / "loop-s1.json").read_text(encoding="utf-8"))
    assert max(counts.values()) >= 5

    r = run_dispatch("harness-trace-analyze", proj, extra_args=["--json"])
    assert r.returncode == 0, r.stderr
    metrics = json.loads(r.stdout)
    assert "loopy.py" in metrics["top_churn"][0]["file"]
    assert any(s["type"] == "high_churn" for s in metrics["signals"]), (
        "5 edits of one file must surface as a high_churn signal"
    )


def test_s3_stop_gate_strict_vs_advisory(tmp_path):
    failing_gate = {"gates": [{"name": "always-fail", "command": "exit 1", "blocking": True}]}

    strict = make_project(tmp_path / "strict", extra_config=failing_gate)
    r = run_dispatch("stop-verify", strict, stdin=json.dumps({"cwd": str(strict)}))
    assert r.returncode == 2
    assert "pre-completion gate failed" in r.stderr
    assert _events(strict, "session_end")[-1]["result"] == "failed"
    # The orchestrator must also emit per-gate trace records (the analyzer's input).
    gates = _events(strict, "gate")
    assert gates and gates[-1]["name"] == "always-fail" and gates[-1]["ok"] is False

    advisory = make_project(
        tmp_path / "advisory", extra_config={**failing_gate, "verificationMode": "advisory"})
    r = run_dispatch("stop-verify", advisory, stdin=json.dumps({"cwd": str(advisory)}))
    assert r.returncode == 0, "advisory mode must report but never block"
    assert "advisory mode — not blocking" in r.stderr
    assert _events(advisory, "session_end")[-1]["result"] == "advisory_fail"


def test_s4_compact_resume_exactly_once(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs" / "plans" / "active" / "p1.md").write_text(
        "# p1\n- [x] step a\n- [ ] step b\n", encoding="utf-8")
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "trace.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "gate", "name": "tsc", "ok": False}) + "\n")
        fh.write(json.dumps({"event": "session_end", "result": "failed"}) + "\n")

    assert run_dispatch("pre-compact", proj, stdin=json.dumps({"cwd": str(proj)})).returncode == 0
    snap = json.loads((state / "pre-compact-snapshot.json").read_text(encoding="utf-8"))
    assert snap["plans"] == [{"name": "p1.md", "checked": 1, "total": 2}]
    assert snap["recentFailedGates"] == ["tsc"]
    assert (state / "pre-compact.dirty").exists()

    # First prompt after compaction re-injects the snapshot…
    r = run_dispatch("user-prompt", proj, stdin=json.dumps({"cwd": str(proj)}))
    ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
    assert "p1.md" in ctx and "tsc" in ctx
    assert not (state / "pre-compact.dirty").exists()

    # …and exactly once: the next prompt is silent.
    r = run_dispatch("user-prompt", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_s4b_session_start_supersedes_resume(tmp_path):
    proj = make_project(tmp_path)
    (proj / "docs" / "plans" / "active" / "p1.md").write_text(
        "# p1\n- [x] a\n- [ ] b\n", encoding="utf-8")
    assert run_dispatch("pre-compact", proj, stdin=json.dumps({"cwd": str(proj)})).returncode == 0
    dirty = proj / ".harness" / "state" / "pre-compact.dirty"
    assert dirty.exists()

    r = run_dispatch("session-start", proj, stdin=json.dumps({"cwd": str(proj)}))
    ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
    assert "Resuming — unfinished from before:" in ctx
    assert not dirty.exists(), "a fresh session start supersedes the mid-session re-inject"


def test_s5_trace_completeness_and_metrics(tmp_path):
    proj = make_project(tmp_path)
    state = proj / ".harness" / "state"
    state.mkdir(parents=True, exist_ok=True)
    records = (
        [{"event": "session_start"}]
        + [{"event": "tool_call", "tool": "Edit", "file": "a.py"}] * 3
        + [{"event": "gate", "name": "lint", "ok": True}] * 5
        + [{"event": "evaluator", "dims": {"visual": 2}, "verdict": "FAIL"}] * 3
        + [{"event": "session_end", "result": "passed"}]
    )
    with open(state / "trace.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    r = run_dispatch("harness-trace-analyze", proj, extra_args=["--json"])
    assert r.returncode == 0, r.stderr
    m = json.loads(r.stdout)
    assert m["sessions_started"] == 1 and m["sessions_ended"] == 1
    assert m["gate_passed"] == 1  # session_end result=passed
    assert m["repeated_tools"] == ["Edit"]
    assert m["gate_outcomes"]["lint"] == {"runs": 5, "fails": 0}
    assert any("failed 0/5" in s for s in m["suggestions"])
    assert any("rubric may be too strict" in s for s in m["suggestions"])


def test_s6_init_to_verify_green(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    (proj / "package.json").write_text('{ "name": "x", "version": "0.0.0" }\n', encoding="utf-8")

    r = run_dispatch("harness-init", proj, extra_args=["--lang", "en"])  # web auto-detected from package.json
    assert r.returncode == 0, r.stdout + r.stderr
    assert "type=web" in r.stdout
    for rel in (".harness/config.json", ".harness/rubric.md", "CLAUDE.md",
                ".harness/hooks/pre-commit", "docs/plans/_template.md"):
        assert (proj / rel).exists(), f"init must scaffold {rel}"

    r = run_dispatch("harness-verify", proj)
    assert r.returncode == 0, r.stdout
    assert "[ok]   claude-md-budget" in r.stdout
    assert "[FAIL]" not in r.stdout, "fresh init must verify green (toolless gates self-skip)"


def test_s7_evaluator_recipe_and_effort_routing(tmp_path):
    extra = {
        "plan": {"codeGlob": r"\.py$"},
        "evaluator": {"enabled": True, "rubricPath": ".harness/rubric.md"},
        "verificationRecipe": {"quality": "run the linter"},
    }
    proj = make_project(tmp_path, extra_config=extra)
    f = proj / "app.py"
    f.write_text("a = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "base"], check=True)
    f.write_text("a = 2\n", encoding="utf-8")  # unstaged change matching codeGlob

    r = run_dispatch("stop-verify", proj, stdin=json.dumps({"cwd": str(proj)}))
    assert r.returncode == 0, r.stderr
    assert "[evaluator] code changed" in r.stderr
    assert "verification recipe (dimension → check):" in r.stderr
    assert "quality: run the linter" in r.stderr

    # Effort routing defers the evaluator nudge and skips full-tier gates.
    routed = make_project(
        tmp_path / "routed",
        extra_config={
            **extra,
            "effortRouting": {"enabled": True},
            "gates": [{"name": "slow", "command": "true", "blocking": True, "tier": "full"}],
        },
    )
    g = routed / "app.py"
    g.write_text("a = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(routed), "add", "."], check=True)
    subprocess.run(["git", "-C", str(routed), "commit", "-q", "-m", "base"], check=True)
    g.write_text("a = 2\n", encoding="utf-8")

    r = run_dispatch(
        "stop-verify", routed,
        stdin=json.dumps({"cwd": str(routed)}),
        extra_env={"CLAUDE_EFFORT": "low"},
    )
    assert r.returncode == 0, r.stderr
    assert "deferred at effort=low" in r.stderr
    assert "[routed-skip]" in r.stderr, "full-tier gate must be route-skipped at low effort"
