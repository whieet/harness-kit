"""dev_e2e_check.py — assertion + evidence engine for the live headless e2e.

scripts/dev-e2e.sh drives real `claude -p` sessions; ALL judgement lives here so
the bash stays a thin orchestrator. Hard assertions prefer filesystem side
effects (trace.jsonl, plan files, loop counters); the only stream-read hard
checks are plugin-load and run-completion, which come from the stable
`system/init` and `result` events. Hook lifecycle events in the stream are
corroborating soft evidence only, since `--include-hook-events` is a newer CLI
surface.

Subcommands:
  probe          --out DIR --proj DIR     gate the two empirical assumptions
  scenario SC-N  --out DIR --proj DIR [--min-starts N]
                                          check one scenario, write evidence-SC-N.json
  merge          --out DIR [--pytest S]   sc-*/evidence-*.json -> evidence.json
  audit-prompt   --out DIR --rubric PATH  print the judge prompt to stdout
  audit-merge    --out DIR                judge-*.json -> audit.json (judge-majority vote)

Exit codes: 0 = all hard assertions passed; 1 = a hard assertion (or a
judge-majority fail on a rubric row) failed; 2 = usage error; 3 = inconclusive
(the run was aborted by upstream throttling — re-run later).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path


# --- stream-json helpers -------------------------------------------------------


def load_stream(path: Path) -> list[dict]:
    events = []
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def result_event(events: list[dict]) -> dict:
    for e in events:
        if e.get("type") == "result":
            return e
    return {}


_THROTTLE_RE = re.compile(
    r"API Error: (429|529)|temporarily limiting requests|quota exhausted|overloaded", re.I)


def _is_throttle(payload: dict) -> bool:
    """ONLY genuine upstream throttling counts — auth/billing/server errors must
    fail loudly, not hide behind the 'inconclusive, re-run later' exit."""
    if not payload.get("is_error"):
        return False
    if payload.get("api_error_status") in (429, 529):
        return True
    return bool(_THROTTLE_RE.search(payload.get("result") or ""))


def rate_limited(events: list[dict]) -> bool:
    """A run aborted by upstream throttling proves nothing about the harness."""
    return _is_throttle(result_event(events))


def hook_responses(events: list[dict], hook_event: str | None = None) -> list[dict]:
    out = []
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "hook_response":
            if hook_event is None or e.get("hook_event") == hook_event:
                out.append(e)
    return out


def plugin_loaded(events: list[dict], name: str = "harness-kit") -> bool:
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            plugins = e.get("plugins") or []
            if any(p.get("name") == name for p in plugins) and not e.get("plugin_errors"):
                return True
    return False


def handoff_injected(events: list[dict]) -> bool:
    return any(
        "Session Handoff (harness-kit)" in (h.get("output") or "")
        for h in hook_responses(events, "SessionStart")
    )


# --- project artifact helpers --------------------------------------------------


def read_trace(proj: Path) -> list[dict]:
    trace = proj / ".harness" / "state" / "trace.jsonl"
    records = []
    if trace.is_file():
        for line in trace.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def trace_events(proj: Path, name: str) -> list[dict]:
    return [r for r in read_trace(proj) if r.get("event") == name]


def plan_files(proj: Path) -> list[Path]:
    out = []
    for sub in ("active", "completed"):
        for p in (proj / "docs" / "plans" / sub).glob("*.md"):
            if p.name != "_template.md":
                out.append(p)
    return out


def loop_counts(proj: Path) -> dict[str, int]:
    merged: dict[str, int] = {}
    for f in glob.glob(str(proj / ".harness" / "state" / "loop-*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for k, v in d.items():
            try:
                merged[k] = max(merged.get(k, 0), int(v))
            except (TypeError, ValueError):
                pass
    return merged


# --- scenario checks -----------------------------------------------------------
# Each returns (hard: dict[str,bool], soft: dict[str,bool], notes: list[str]).


def check_probe(proj: Path, events: list[dict]):
    hard = {
        "plugin_loaded_no_errors": plugin_loaded(events),
        "session_start_in_trace": len(trace_events(proj, "session_start")) >= 1,
    }
    soft = {
        "hook_events_in_stream": bool(hook_responses(events)),
        "handoff_injected": handoff_injected(events),
    }
    return hard, soft, []


def check_sc1(proj: Path, events: list[dict]):
    hard = {
        "config_scaffolded": (proj / ".harness" / "config.json").is_file(),
        "claude_md_scaffolded": (proj / "CLAUDE.md").is_file()
        or (proj / ".claude" / "CLAUDE.md").is_file(),
        "precommit_scaffolded": (proj / ".harness" / "hooks" / "pre-commit").is_file(),
        "run_completed": not result_event(events).get("is_error", True),
    }
    # SessionStart fired before init ran, when the plugin was correctly inert —
    # so the meaningful soft signals are the hooks coming alive POST-init.
    gates_ok = [r for r in trace_events(proj, "gate") if r.get("ok")]
    soft = {
        "rubric_scaffolded": (proj / ".harness" / "rubric.md").is_file(),
        "post_init_session_end": len(trace_events(proj, "session_end")) >= 1,
        "claude_md_budget_gate_ran": any(r.get("name") == "claude-md-budget" for r in gates_ok),
    }
    return hard, soft, []


def check_sc2(proj: Path, events: list[dict]):
    hello = proj / "hello.py"
    plans = plan_files(proj)
    hard = {
        "hello_py_written": hello.is_file() and "greet" in hello.read_text(encoding="utf-8"),
        "plan_scaffolded": bool(plans),
        "session_start_in_trace": len(trace_events(proj, "session_start")) >= 1,
        "session_end_in_trace": len(trace_events(proj, "session_end")) >= 1,
    }
    dod_done, progress_logged = False, False
    for p in plans:
        text = p.read_text(encoding="utf-8")
        if re.search(r"^- \[[xX]\]", text, re.M) and not re.search(r"^- \[ \]", text, re.M):
            dod_done = True
        m = re.search(r"## Progress log\n(.*?)(\n## |\Z)", text, re.S)
        # >1 bullet means the model logged steps beyond the scaffold's seed line.
        if m and len(re.findall(r"^- ", m.group(1), re.M)) >= 2:
            progress_logged = True
    soft = {
        "dod_fully_checked": dod_done,
        "progress_log_updated": progress_logged,
        "tool_calls_traced": len(trace_events(proj, "tool_call")) >= 1,
        "budget_gate_ran_in_trace": any(
            r.get("name") == "claude-md-budget" and r.get("ok")
            for r in trace_events(proj, "gate")),
        "handoff_injected": handoff_injected(events),
        "finished_clean": (trace_events(proj, "session_end") or [{}])[-1].get("result") == "passed",
    }
    return hard, soft, [f"plans: {[p.name for p in plans]}"]


def check_sc3(proj: Path, events: list[dict]):
    ends = [r.get("result") for r in trace_events(proj, "session_end")]
    hard = {
        "gate_remediation_done": (proj / "FIXED").exists(),
        "blocked_then_passed": "failed" in ends and ends[-1] == "passed",
    }
    soft = {
        "stop_hook_exit_2_seen": any(
            h.get("exit_code") == 2 for h in hook_responses(events, "Stop")),
        "task_file_written": (proj / "done.txt").is_file(),
    }
    return hard, soft, [f"session_end timeline: {ends}"]


def check_sc4(proj: Path, events: list[dict]):
    counts = loop_counts(proj)
    top = max(counts.values()) if counts else 0
    hard = {"loop_counter_reached_threshold": top >= 3}
    soft = {
        "counter_file_is_top_churn": any(k.endswith("counter.py") for k, v in counts.items()
                                         if v == top),
        "loop_warning_surfaced": any(
            "Loop detection" in (h.get("stderr") or "") + (h.get("output") or "")
            for h in hook_responses(events)),
    }
    return hard, soft, [f"loop counts: {counts}"]


def _subagent_dispatched(events: list[dict], needle: str) -> bool:
    """True if an assistant tool_use block actually dispatched a subagent whose
    type/prompt mentions `needle` — NOT a substring scan of the whole stream
    (the advisor dashboard and command docs mention 'evaluator' on every run)."""
    for e in events:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") in ("Task", "Agent") and needle in json.dumps(
                    block.get("input") or {}, ensure_ascii=False):
                return True
    return False


def check_sc5(proj: Path, events: list[dict]):
    res = result_event(events)
    hard = {"run_completed": not res.get("is_error", True)}
    soft = {
        "verdict_returned": "VERDICT" in (res.get("result") or ""),
        "evaluator_trace_event": len(trace_events(proj, "evaluator")) >= 1,
        "evaluator_dispatched": _subagent_dispatched(events, "evaluator"),
    }
    return hard, soft, []


# Set from --min-starts: SC-6 reuses SC-2's project, and SC-5 may have run there
# too, so "a new session started" must be judged against a counted baseline.
MIN_SESSION_STARTS = 2


def check_sc6(proj: Path, events: list[dict]):
    res = result_event(events)
    plans = " ".join(p.stem for p in plan_files(proj))
    answer = res.get("result") or ""
    hard = {
        "new_session_started": len(trace_events(proj, "session_start")) >= MIN_SESSION_STARTS,
        "run_completed": not res.get("is_error", True),
    }
    soft = {
        "handoff_injected": handoff_injected(events),
        "answer_references_last_work": any(
            tok and tok in answer for tok in plans.split() + ["hello"]),
    }
    return hard, soft, [f"required session_start count >= {MIN_SESSION_STARTS}"]


CHECKS = {
    "probe": check_probe,
    "SC-1": check_sc1,
    "SC-2": check_sc2,
    "SC-3": check_sc3,
    "SC-4": check_sc4,
    "SC-5": check_sc5,
    "SC-6": check_sc6,
}


# --- evidence / audit ----------------------------------------------------------


def _report(sid: str, hard: dict, soft: dict, notes: list[str], info: dict) -> dict:
    for name, ok in hard.items():
        print(f"  [{'ok' if ok else 'FAIL'}]   {sid}:{name}")
    for name, ok in soft.items():
        print(f"  [{'ok' if ok else 'warn'}] ~ {sid}:{name}")
    for n in notes:
        print(f"  note: {n}")
    return {"id": sid, "hard": hard, "soft": soft, "notes": notes, "info": info}


def cmd_scenario(sid: str, out: Path, proj: Path) -> int:
    events = load_stream(out / "run.jsonl")
    hard, soft, notes = CHECKS[sid](proj, events)
    res = result_event(events)
    info = {
        "cost_usd": res.get("total_cost_usd"),
        "num_turns": res.get("num_turns"),
        "is_error": res.get("is_error"),
        "session_id": res.get("session_id"),
    }
    if rate_limited(events):
        # Inconclusive, not a harness failure — exit 3 so the orchestrator can
        # stop burning quota and report "re-run later" instead of a false FAIL.
        notes = notes + [f"ABORTED by rate limit: {(res.get('result') or '')[:120]}"]
        evidence = _report(sid, hard, soft, notes, info)
        evidence["aborted"] = "rate_limited"
        (out / f"evidence-{sid}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [INCONCLUSIVE] {sid}: upstream rate limit — evidence kept, run not judged")
        return 3
    evidence = _report(sid, hard, soft, notes, info)
    (out / f"evidence-{sid}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(hard.values()) else 1


def cmd_merge(out: Path, pytest_summary: str | None) -> int:
    scenarios = []
    for f in sorted(glob.glob(str(out / "*" / "evidence-*.json"))) + sorted(
            glob.glob(str(out / "evidence-probe.json"))):
        scenarios.append(json.loads(Path(f).read_text(encoding="utf-8")))
    merged = {
        "deterministic_suite": pytest_summary or "(not run in this invocation)",
        "scenarios": scenarios,
        "summary": {
            "hard_passed": sum(1 for s in scenarios for ok in s["hard"].values() if ok),
            "hard_total": sum(len(s["hard"]) for s in scenarios),
            "soft_passed": sum(1 for s in scenarios for ok in s["soft"].values() if ok),
            "soft_total": sum(len(s["soft"]) for s in scenarios),
            "total_cost_usd": round(sum(
                s["info"].get("cost_usd") or 0 for s in scenarios), 4),
        },
    }
    (out / "evidence.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(merged["summary"], ensure_ascii=False))
    return 0


def cmd_audit_prompt(out: Path, rubric: Path) -> int:
    evidence = (out / "evidence.json").read_text(encoding="utf-8")
    sys.stdout.write(
        "You are an independent harness-engineering auditor. Score the harness-kit "
        "plugin against the rubric below, using ONLY the captured evidence — do not "
        "assume anything not evidenced.\n\n"
        "Rules:\n"
        "- One verdict per rubric row id: pass | partial | fail | n-a.\n"
        "- `deterministic_suite` attests every rubric evidence pointer that names a "
        "pytest test id (test_*) — if the suite is green, those pointers count as "
        "satisfied evidence.\n"
        "- Live evidence: `hard`/`soft` assertion booleans per scenario (SC-1..SC-6, "
        "probe). A rubric row whose live scenario evidence is missing or false → "
        "partial or fail; n-a only when the run did not include that scenario.\n"
        "- Output ONLY a JSON array: "
        '[{"id":"O1","verdict":"pass","evidence":"<one-line pointer>"}] — one entry '
        "per rubric row, no prose around it.\n\n"
        "=== RUBRIC ===\n" + rubric.read_text(encoding="utf-8") +
        "\n\n=== EVIDENCE ===\n" + evidence + "\n")
    return 0


def _extract_array(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def cmd_audit_merge(out: Path) -> int:
    judges = []
    for f in sorted(glob.glob(str(out / "judge-*.json"))):
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        body = payload.get("result") or ""
        arr = _extract_array(body)
        if arr:
            judges.append({
                str(r.get("id")).strip().upper(): r
                for r in arr if isinstance(r, dict) and r.get("id")
            })
        elif _is_throttle(payload):
            print(f"  warn: {os.path.basename(f)} was rate-limited — no verdicts")
        else:
            print(f"  warn: could not parse verdicts from {os.path.basename(f)}")
    if not judges:
        print("  warn: no parseable judge output — audit skipped (not failing the run)")
        (out / "audit.json").write_text(
            json.dumps({"judges": 0, "rows": [], "failing": [],
                        "note": "no parseable judge output"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return 0

    # Majority is denominated by the number of JUDGES, not by votes cast on a
    # row — otherwise a single judge's hallucinated/mis-cased row id would count
    # as a unanimous verdict and could fail the whole suite.
    ids = sorted({i for j in judges for i in j})
    rows, failing = [], []
    for rid in ids:
        verdicts = [str(j[rid].get("verdict", "n-a")).strip().lower()
                    for j in judges if rid in j]
        tally = {v: verdicts.count(v) for v in set(verdicts)}
        final = max(tally, key=lambda v: tally[v])
        disputed = tally.get(final, 0) <= len(judges) // 2
        rows.append({
            "id": rid,
            "verdict": "disputed" if disputed else final,
            "votes": verdicts,
            "evidence": [j[rid].get("evidence", "") for j in judges if rid in j],
        })
        if not disputed and final == "fail":
            failing.append(rid)

    audit = {"judges": len(judges), "rows": rows, "failing": failing}
    (out / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"  [{r['verdict']:^8}] {r['id']}  votes={r['votes']}")
    if failing:
        print(f"  ❌ audit: majority-fail rows: {failing}")
        return 1
    print(f"  ✅ audit: no majority-fail rows across {len(judges)} judges")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]

    def opt(name: str, default: str | None = None) -> str | None:
        return rest[rest.index(name) + 1] if name in rest else default

    out = Path(opt("--out", "."))
    if cmd == "probe":
        proj = Path(opt("--proj"))
        events = load_stream(out / "probe.jsonl")
        hard, soft, notes = check_probe(proj, events)
        if rate_limited(events):
            notes = notes + ["ABORTED by rate limit"]
        evidence = _report("probe", hard, soft, notes,
                           {"cost_usd": result_event(events).get("total_cost_usd")})
        if rate_limited(events):
            evidence["aborted"] = "rate_limited"
        (out / "evidence-probe.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        if rate_limited(events):
            print("  [INCONCLUSIVE] probe: upstream rate limit")
            return 3
        return 0 if all(hard.values()) else 1
    if cmd == "scenario":
        global MIN_SESSION_STARTS
        if opt("--min-starts"):
            MIN_SESSION_STARTS = int(opt("--min-starts"))
        return cmd_scenario(rest[0], out, Path(opt("--proj")))
    if cmd == "merge":
        return cmd_merge(out, opt("--pytest"))
    if cmd == "audit-prompt":
        return cmd_audit_prompt(out, Path(opt("--rubric")))
    if cmd == "audit-merge":
        return cmd_audit_merge(out)
    print(f"unknown subcommand: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
