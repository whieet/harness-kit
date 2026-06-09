"""util.py — small cross-platform helpers shared by hooks and commands."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


# ----------------------------------------------------------------- text ----
def indent(text: str, prefix: str = "  ") -> str:
    """Prefix each line of text (replaces `sed 's/^/  /'`).

    Preserves a trailing newline-less last line. Empty input returns empty.
    """
    if not text:
        return ""
    lines = text.split("\n")
    return "\n".join(prefix + line for line in lines)


# ------------------------------------------------------------------- time ----
def iso_utc() -> str:
    """Return now() as YYYY-MM-DDTHH:MM:SSZ (matches `date -u +...` everywhere)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_ymd() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def time_hms_compact() -> str:
    return datetime.now().strftime("%H%M%S")


def timestamp_minute() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------ hook output ----
def emit_hook_context(event: str, ctx_text: str) -> None:
    """Print the documented additionalContext JSON for a Claude Code hook.

    Identical shape to what every existing on-*.sh emits.
    """
    if not ctx_text:
        return
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": ctx_text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


# ----------------------------------------------------------- trace events ----
def append_trace(state_dir: str, record: dict[str, Any]) -> None:
    """Append one JSONL record to state_dir/trace.jsonl, swallowing all errors.

    Trace writes must never fail a hook (the upstream bash uses `|| true`).
    """
    if "ts" not in record:
        record = {"ts": iso_utc(), **record}
    path = os.path.join(state_dir, "trace.jsonl")
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            # Compact separators match what the bash impl wrote via
            # `printf '{"ts":"%s",...}'` — preserves byte-level continuity for
            # any consumer that diffs the trace across upgrades.
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------ process ck ----
def process_running(name: str) -> bool:
    """Cross-platform replacement for `pgrep -q "$name"`.

    Used by harness-verify's gate.skipWhenProcess (e.g. skip godot compile when
    the Godot editor is running and would lock the project).
    """
    if not name:
        return False
    if platform.system() == "Windows":
        # tasklist matches by exact image name; users typically supply 'godot' or
        # 'Godot', so try both an exact match and a wildcarded fallback.
        cmd_exact = ["tasklist", "/FI", f"IMAGENAME eq {name}.exe", "/NH", "/FO", "CSV"]
        try:
            r = subprocess.run(cmd_exact, capture_output=True, text=True, check=False)
        except (FileNotFoundError, OSError):
            return False
        if r.returncode == 0 and name.lower() in r.stdout.lower():
            return True
        # Fallback: WMIC-style substring filter via PowerShell Get-Process.
        try:
            r2 = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -like '*{name}*' }} | Select-Object -First 1"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return False
        return r2.returncode == 0 and bool(r2.stdout.strip())
    # Unix: pgrep returns 0 when at least one process matches. We deliberately
    # do NOT pass -f: the original bash used `pgrep -q "$name"` which matches
    # the process *name* (basename of comm) only — passing -f would also match
    # any process whose full command line happens to contain the substring
    # (including our own running bash/python invocation), silently skipping
    # gates that should have run.
    try:
        r = subprocess.run(
            ["pgrep", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


# ------------------------------------------------------------ regex group ----
def regex_search(pattern: str, text: str) -> bool:
    """re.search returning False on invalid pattern (mirrors grep -qE)."""
    import re

    if not pattern:
        return False
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False


# ---------------------------------------------------------------- writers ----
def write_text(path: str, content: str) -> None:
    """Write text atomically-ish: ensure parent dir exists, UTF-8, no BOM."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def chmod_x(path: str) -> None:
    """chmod +x where the platform supports it; no-op on Windows."""
    if platform.system() == "Windows":
        return
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | 0o111)
    except OSError:
        pass


def is_executable(path: str) -> bool:
    """os.access X_OK; on Windows always True if file exists (no exec bit)."""
    if platform.system() == "Windows":
        return os.path.isfile(path)
    return os.path.isfile(path) and os.access(path, os.X_OK)


# ------------------------------------------------------------ small i/o ----
def safe_read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def list_plans(active_dir: str) -> list[str]:
    """Active plans = *.md under active_dir (maxdepth 1), excluding .gitkeep."""
    if not os.path.isdir(active_dir):
        return []
    out: list[str] = []
    try:
        for name in sorted(os.listdir(active_dir)):
            if not name.endswith(".md"):
                continue
            if name == ".gitkeep":
                continue
            full = os.path.join(active_dir, name)
            if os.path.isfile(full):
                out.append(full)
    except OSError:
        return []
    return out


# ------------------------------------------------------------------ misc ----
def writeln_stderr(s: str = "") -> None:
    sys.stderr.write(s + "\n")
