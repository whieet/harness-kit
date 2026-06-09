"""gitutil.py — thin, swallow-errors wrapper around the git CLI.

git is the only external dependency we assume beyond Python (it is required
on every supported OS — on Windows it ships via Git for Windows, which also
provides the Bash that runs the hook launchers).
"""
from __future__ import annotations

import subprocess


def _run(args: list[str], cwd: str | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout


def branch(cwd: str | None = None) -> str:
    out = _run(["branch", "--show-current"], cwd).strip()
    return out or "unknown"


def diff_name_only(cwd: str | None = None) -> str:
    return _run(["diff", "--name-only"], cwd)


def diff_staged_name_only(cwd: str | None = None) -> str:
    return _run(["diff", "--staged", "--name-only"], cwd)


def untracked(cwd: str | None = None) -> str:
    return _run(["ls-files", "--others", "--exclude-standard"], cwd)


def log_oneline(n: int = 5, cwd: str | None = None) -> str:
    out = _run(["log", "--oneline", f"-{n}"], cwd).rstrip("\n")
    return out or "(no commits)"


def diff_numstat(cwd: str | None = None) -> str:
    return _run(["diff", "--numstat"], cwd)


def diff_staged_numstat(cwd: str | None = None) -> str:
    return _run(["diff", "--staged", "--numstat"], cwd)


def is_inside_worktree(cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def set_hooks_path(path: str, cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(
            ["git", "config", "core.hooksPath", path],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return False
    return r.returncode == 0


def count_lines(text: str) -> int:
    """Mirror `... | wc -l` — count of trailing newlines (matches old behavior)."""
    if not text:
        return 0
    # `git diff --name-only` always terminates each path with \n; wc -l counts
    # those terminators, so just count them.
    return text.count("\n")
