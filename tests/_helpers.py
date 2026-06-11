"""Shared test fixtures and helpers.

Tests build a fresh fixture project in a tmpdir (git-init'd, with a config),
then drive the dispatcher / bin launchers via these env-controlled helpers.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
BIN = REPO_ROOT / "bin"


def make_project(tmp_path: Path, with_config: bool = True, extra_config: dict | None = None) -> Path:
    """Create a project under tmp_path/proj with .harness/config.json and git init."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(proj)], check=True)
    # User config required for commits/operations that touch git.
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(proj), "config", k, v], check=True)
    if with_config:
        h = proj / ".harness"
        h.mkdir()
        cfg = {
            "projectType": "custom",
            "verificationMode": "strict",
            "gates": [],
            "plan": {
                "dir": "docs/plans",
                "codeGlob": r"\.(py|gd)$",
                "statusField": "status",
                "completedValue": "completed",
                "checklistRegex": r"^- \[ \]",
            },
            "docs": {"scanRoots": ["docs"]},
            "metrics": [],
            "loopDetection": {"threshold": 3},
            "enabledCapabilities": {
                "planGate": True,
                "loopDetection": True,
                "toolTrace": True,
                "evaluator": True,
                "contextSnapshot": True,
                "evaluatorAutoDispatch": False,
            },
            "effortRouting": {"enabled": False},
        }
        if extra_config:
            _deep_merge(cfg, extra_config)
        (h / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        (h / ".gitignore").write_text("state/\n", encoding="utf-8")
        # Plan dirs
        for sub in ("active", "completed"):
            (proj / "docs" / "plans" / sub).mkdir(parents=True, exist_ok=True)
            (proj / "docs" / "plans" / sub / ".gitkeep").touch()
    # Initial commit so git log/branches behave.
    (proj / "README.md").write_text("# proj\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "init"], check=True)
    return proj


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


def run_dispatch(
    dispatch: str,
    proj: Path,
    stdin: str = "",
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the new Python dispatcher in `proj` cwd."""
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    env["HARNESS_PROJECT_DIR"] = str(proj)
    if extra_env:
        env.update(extra_env)
    cmd = [sys.executable, str(SCRIPTS / "harness_main.py"), dispatch]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False, encoding="utf-8", errors="replace")


def read_trace(proj: Path) -> list[dict]:
    """Parse .harness/state/trace.jsonl into a list of records (empty if absent)."""
    trace = proj / ".harness" / "state" / "trace.jsonl"
    if not trace.is_file():
        return []
    records = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def edit_payload(proj: Path, file_path: Path, sid: str = "s1", tool: str = "Edit") -> str:
    """Hook stdin JSON for an edit-shaped tool event."""
    return json.dumps({
        "cwd": str(proj),
        "session_id": sid,
        "tool_name": tool,
        "tool_input": {"file_path": str(file_path)},
    })


def run_bin(name: str, proj: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Invoke a bin launcher (uses the dispatcher under the hood)."""
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    cmd = ["bash", str(BIN / name)]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=str(proj),
        capture_output=True,
        text=True,
        env=env,
        check=False, encoding="utf-8", errors="replace")
