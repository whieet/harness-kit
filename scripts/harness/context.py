"""context.py — project resolution, config loader, capability gates.

Replaces scripts/lib/config.sh + scripts/lib/enabled.sh. Every hook and command
constructs a HarnessContext at entry and consults it throughout.

Resolution order (matches the old harness_resolve_project_dir):
  1. cwd carried in the hook payload (when init_from_stdin is called)
  2. $HARNESS_PROJECT_DIR
  3. $CLAUDE_PROJECT_DIR (injected by Claude Code)
  4. git rev-parse --show-toplevel from cwd
  5. walk up from cwd looking for .harness/ or .git/
  6. cwd
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Capabilities default ON unless they live in this set (matches config.sh:84).
EXPERIMENTAL_OFF: set[str] = {"evaluatorAutoDispatch"}


def _git_toplevel(cwd: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


def _walk_up_for_marker(start: str) -> str | None:
    d = os.path.abspath(start)
    while d and d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".harness")) or os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return None


def resolve_project_dir(payload_cwd: str | None = None) -> str:
    """Return the absolute project root path."""
    if payload_cwd and os.path.isdir(payload_cwd):
        top = _git_toplevel(payload_cwd)
        if top:
            return top
        return os.path.abspath(payload_cwd)
    env_proj = os.environ.get("HARNESS_PROJECT_DIR")
    if env_proj:
        return env_proj
    env_claude = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_claude:
        return env_claude
    top = _git_toplevel(os.getcwd())
    if top:
        return top
    found = _walk_up_for_marker(os.getcwd())
    if found:
        return found
    return os.getcwd()


@dataclass
class HarnessContext:
    """Resolved project paths + parsed .harness/config.json."""

    project_dir: str
    config_path: str
    config: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    stdin_raw: str = ""

    # ------------------------------------------------------------------ paths
    @property
    def harness_dir(self) -> str:
        return os.path.join(self.project_dir, ".harness")

    def state_dir(self) -> str:
        d = os.path.join(self.harness_dir, "state")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def has_config(self) -> bool:
        return os.path.isfile(self.config_path)

    # ---------------------------------------------------------------- config
    def reload_config(self) -> None:
        self.config = {}
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self.config = loaded
            except (OSError, json.JSONDecodeError):
                self.config = {}

    def cfg_get(self, dotted: str, default: Any = "") -> Any:
        """Look up a dotted path in config. Returns default for missing keys.

        Mirrors harness_cfg_get from config.sh: scalars are returned raw,
        non-scalars are JSON-encoded so callers always get a string when they
        request a string-shaped default.
        """
        cur: Any = self.config
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        if cur is None:
            return default
        return cur

    def cfg_get_str(self, dotted: str, default: str = "") -> str:
        v = self.cfg_get(dotted, None)
        if v is None:
            return default
        if isinstance(v, str):
            return v
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return json.dumps(v, ensure_ascii=False)

    def language(self) -> str:
        """Project language preference for user-facing text and generated docs."""
        raw = self.cfg_get_str("language", self.cfg_get_str("lang", "en")).lower()
        return raw if raw in ("en", "zh") else "en"

    def language_directive(self) -> str:
        if self.language() == "zh":
            return (
                "语言偏好：中文。请使用中文与用户交互，并用中文编写生成的文档内容，"
                "除非用户明确要求其他语言。不要翻译文件名、目录名、命令名或配置键。"
            )
        return (
            "Language preference: English. Respond to the user and write generated "
            "documentation in English unless the user explicitly requests otherwise. "
            "Do not translate file/directory names, command names, or config keys."
        )

    def tr(self, en: str, zh: str) -> str:
        return zh if self.language() == "zh" else en

    def cap_enabled(self, name: str) -> bool:
        """Stable caps default ON; experimental caps default OFF."""
        caps = self.config.get("enabledCapabilities") or {}
        default = name not in EXPERIMENTAL_OFF
        v = caps.get(name, default)
        return bool(v)

    # ------------------------------------------------------------------ env
    def export_env(self) -> None:
        """Set HARNESS_PROJECT_DIR / HARNESS_CONFIG for child processes."""
        os.environ["HARNESS_PROJECT_DIR"] = self.project_dir
        os.environ["HARNESS_CONFIG"] = self.config_path


def _parse_stdin_payload(raw: str) -> tuple[dict[str, Any], str | None]:
    """Returns (parsed_json_or_empty, cwd_from_payload_or_None)."""
    if not raw:
        return {}, None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}, None
    if not isinstance(data, dict):
        return {}, None
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = None
    return data, cwd


def load_context(stdin_raw: str = "") -> HarnessContext:
    """Build a HarnessContext from optional stdin event JSON.

    Pass the full raw stdin string; this function parses it and uses the cwd
    inside (if present) to anchor project resolution.
    """
    payload, payload_cwd = _parse_stdin_payload(stdin_raw)
    proj = resolve_project_dir(payload_cwd)
    cfg_path = os.path.join(proj, ".harness", "config.json")
    ctx = HarnessContext(
        project_dir=proj,
        config_path=cfg_path,
        payload=payload,
        stdin_raw=stdin_raw,
    )
    ctx.reload_config()
    ctx.export_env()
    return ctx


def read_stdin() -> str:
    """Read all of stdin, never raising.

    Hooks must tolerate a closed stdin (manual command-line invocation), so
    return '' on any error.
    """
    if sys.stdin is None or sys.stdin.closed:
        return ""
    try:
        if sys.stdin.isatty():
            return ""
    except (ValueError, OSError):
        pass
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def exit_unless_initialized(ctx: HarnessContext) -> None:
    """Equivalent of `harness_has_config || exit 0` in the old shell library.

    The plugin must be completely inert on un-initialized repos.
    """
    if not ctx.has_config():
        sys.exit(0)


def chdir_project(ctx: HarnessContext) -> None:
    """cd to the project root, silently no-op if the path is gone."""
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        sys.exit(0)
