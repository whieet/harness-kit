"""harness-verify — config-driven verification gate orchestrator.

Port of bin/harness-verify. Iterates over config.gates[], runs each gate via
`bash -c "$CMD"` (so the command grammar matches what users wrote in the bash
era; bash is available on every supported OS via Git for Windows on Windows),
prints a uniform [ok]/[FAIL]/[warn] table, and exits non-zero if any blocking
gate failed.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout

from .. import util
from ..context import HarnessContext, load_context


def _bash_cmd() -> str | None:
    """Locate bash. Required for executing gate commands (which are shell strings)."""
    return shutil.which("bash")


def _bundled_bin() -> str:
    """Plugin bin dir, prepended to PATH so bundled gates (e.g. harness-doc-links)
    resolve by bare name when called from a gate.command."""
    env = os.environ.get("HARNESS_KIT_ROOT")
    if env and os.path.isdir(env):
        return os.path.join(env, "bin")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", "bin"))


def _gates(ctx: HarnessContext) -> list[dict]:
    out: list[dict] = []
    for g in ctx.config.get("gates") or []:
        if not isinstance(g, dict):
            continue
        out.append(
            {
                "name": str(g.get("name", "")),
                "blocking": bool(g.get("blocking", True)),
                "skipWhenProcess": str(g.get("skipWhenProcess", "")),
                "tier": str(g.get("tier", "full")),
                "command": str(g.get("command", "")),
            }
        )
    return out


def _run_gate(cmd: str, bash: str, env: dict) -> tuple[int, str]:
    """Run a gate. Returns (returncode, combined-output)."""
    try:
        r = subprocess.run(
            [bash, "-c", cmd],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except (FileNotFoundError, OSError) as e:
        return 127, f"harness-verify: failed to spawn bash: {e}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _emit_trace(ctx: HarnessContext, name: str, ok: bool) -> None:
    if not ctx.cap_enabled("toolTrace"):
        return
    util.append_trace(ctx.state_dir(), {"event": "gate", "name": name, "ok": bool(ok)})


def render(ctx: HarnessContext) -> tuple[str, int]:
    """Run all gates; return (combined-text, exit-code).

    Used by stop_verify.run_capture() so the Stop hook can inline-call the
    orchestrator without shelling out.
    """
    buf = io.StringIO()
    rc = _execute(ctx, buf)
    return buf.getvalue().rstrip("\n"), rc


def _execute(ctx: HarnessContext, out_stream) -> int:
    def emit(s: str = "") -> None:
        out_stream.write(s + "\n")

    if not ctx.has_config():
        emit("harness-verify: no .harness/config.json — run /harness-kit:init. Nothing to verify.")
        return 0

    try:
        os.chdir(ctx.project_dir)
    except OSError:
        emit("harness-verify: cannot cd to project root")
        return 1

    gates = _gates(ctx)
    if not gates:
        emit("harness-verify: no gates configured in .harness/config.json.")
        return 0

    bash = _bash_cmd()
    if not bash:
        emit(
            "harness-verify: bash not found on PATH — gate commands need a POSIX shell. "
            "On Windows install Git for Windows."
        )
        return 1

    # PATH augmentation so bundled gates resolve by bare name.
    env = os.environ.copy()
    env["PATH"] = _bundled_bin() + os.pathsep + env.get("PATH", "")
    env["HARNESS_PROJECT_DIR"] = ctx.project_dir
    env["HARNESS_CONFIG"] = ctx.config_path

    # Effort routing
    route_fast = False
    effort = os.environ.get("CLAUDE_EFFORT", "")
    if ctx.cfg_get_str("effortRouting.enabled", "false") == "true":
        if effort in ("low", "medium"):
            route_fast = True

    overall = 0
    soft_warn = 0
    n = 0
    skipped_full: list[str] = []

    hdr = "==> harness-verify"
    if route_fast:
        hdr += f" (effort={effort} → fast-tier only)"
    emit(hdr)

    for g in gates:
        name = g["name"]
        blocking = g["blocking"]
        skip_proc = g["skipWhenProcess"]
        tier = g["tier"]
        cmd = g["command"]

        if route_fast and tier != "fast":
            skipped_full.append(name)
            continue
        if skip_proc and util.process_running(skip_proc):
            emit(f"  [skip] {name} (process '{skip_proc}' running)")
            continue

        n += 1
        rc, output = _run_gate(cmd, bash, env)
        if rc == 0:
            emit(f"  [ok]   {name}")
            _emit_trace(ctx, name, True)
        else:
            if blocking:
                emit(f"  [FAIL] {name} (rc={rc})")
                overall = 1
            else:
                emit(f"  [warn] {name} (rc={rc}, non-blocking)")
                soft_warn = 1
            if output.strip():
                emit(util.indent(output.rstrip("\n"), "         "))
            _emit_trace(ctx, name, False)

    if skipped_full:
        emit(
            "  [routed-skip] full-tier gates not run at effort=%s:%s "
            "(run at high+ effort or disable effortRouting)"
            % (effort, " " + " ".join(skipped_full))
        )

    emit("")
    if overall:
        emit("==> ❌ harness-verify FAILED")
        return 1
    if soft_warn:
        emit("==> ⚠️  harness-verify passed with soft warnings")
    emit(f"==> ✅ harness-verify OK ({n} gates)")
    return 0


def run_capture(ctx: HarnessContext) -> tuple[str, int]:
    """Convenience: run and capture combined output + rc (used by stop_verify)."""
    return render(ctx)


def run(argv: list[str]) -> int:
    """CLI entry — direct invocation prints to stdout, exits with rc."""
    ctx = load_context("")
    return _execute(ctx, sys.stdout)
