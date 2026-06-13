"""cli.py — dispatcher mapping hook event / command name to handler.

This is the single Python entry the bash launchers exec into. Names match the
existing bin/* command names and the Claude Code hook event names so the
hooks.json / bin layout stays a 1:1 translation.
"""
from __future__ import annotations

import importlib
import sys

# Map dispatcher name -> (module path, function attribute).
# Hook handlers take no argv; command handlers take argv[1:].
HOOKS = {
    "session-start": ("harness.hooks.session_start", "run"),
    "user-prompt": ("harness.hooks.user_prompt", "run"),
    "pre-edit": ("harness.hooks.pre_edit", "run"),
    "post-edit": ("harness.hooks.post_edit", "run"),
    "plan-approved": ("harness.hooks.plan_approved", "run"),
    "post-tool": ("harness.hooks.post_tool", "run"),
    "tool-failure": ("harness.hooks.tool_failure", "run"),
    "pre-compact": ("harness.hooks.pre_compact", "run"),
    "stop-verify": ("harness.hooks.stop_verify", "run"),
}

COMMANDS = {
    "harness-init": ("harness.commands.init", "run"),
    "harness-verify": ("harness.commands.verify", "run"),
    "harness-advisor": ("harness.commands.advisor", "run"),
    "harness-maintenance": ("harness.commands.maintenance", "run"),
    "harness-check-layering": ("harness.commands.check_layering", "run"),
    "harness-check-plan-dod": ("harness.commands.check_plan_dod", "run"),
    "harness-doc-links": ("harness.commands.doc_links", "run"),
    "harness-doc-gardening": ("harness.commands.doc_gardening", "run"),
    "harness-trace-analyze": ("harness.commands.trace_analyze", "run"),
}


def _help() -> int:
    sys.stderr.write(
        "Usage:\n"
        "  harness_main.py <hook-event>            # e.g. session-start, pre-edit\n"
        "  harness_main.py <bin-name> [args]       # e.g. harness-verify, harness-init custom --lang en\n"
        "Known hooks:    " + ", ".join(HOOKS) + "\n"
        "Known commands: " + ", ".join(COMMANDS) + "\n"
    )
    return 2


def main(argv: list[str]) -> int:
    if not argv:
        return _help()
    name = argv[0]
    rest = argv[1:]

    if name in HOOKS:
        mod_name, fn_name = HOOKS[name]
        mod = importlib.import_module(mod_name)
        return int(getattr(mod, fn_name)() or 0)
    if name in COMMANDS:
        mod_name, fn_name = COMMANDS[name]
        mod = importlib.import_module(mod_name)
        return int(getattr(mod, fn_name)(rest) or 0)
    sys.stderr.write(f"harness: unknown subcommand '{name}'\n")
    return _help()
