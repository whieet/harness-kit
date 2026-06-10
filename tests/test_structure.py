"""Structural conformance tests — pure file parsing, no subprocesses.

These pin the cross-file invariants that nothing else enforces: the plugin
manifest, the hooks.json ↔ dispatcher mapping, command/skill doc sync, and
template placeholder contracts. They are the cheapest layer of the test
pyramid (see docs/testing.md) and run on every platform.
"""
from __future__ import annotations

import json
import re

import pytest

from tests._helpers import REPO_ROOT

from harness import cli


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# --- commands/ ↔ skills/ ------------------------------------------------------


def _strip_frontmatter_name(text: str) -> str:
    """Drop the `name:` line inside the leading frontmatter block."""
    lines = text.splitlines(keepends=True)
    out, fences = [], 0
    for ln in lines:
        if ln.rstrip("\n") == "---" and fences < 2:
            fences += 1
            out.append(ln)
            continue
        if fences == 1 and re.match(r"^name:\s", ln):
            continue
        out.append(ln)
    return "".join(out)


def test_commands_skills_in_sync():
    cmd_files = sorted((REPO_ROOT / "commands").glob("*.md"))
    assert cmd_files, "no command docs found"
    for cmd in cmd_files:
        skill = REPO_ROOT / "skills" / cmd.stem / "SKILL.md"
        assert skill.is_file(), f"missing skill for command {cmd.stem}"
        cmd_text = cmd.read_text(encoding="utf-8")
        skill_text = _strip_frontmatter_name(skill.read_text(encoding="utf-8"))
        assert skill_text == cmd_text, (
            f"{cmd.name} and skills/{cmd.stem}/SKILL.md have drifted apart "
            "(they must be identical apart from the SKILL frontmatter `name:` line)"
        )


def test_every_skill_has_a_command():
    skills = {p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    commands = {p.stem for p in (REPO_ROOT / "commands").glob("*.md")}
    assert skills == commands


# --- hooks.json ↔ dispatcher --------------------------------------------------

_KNOWN_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "UserPromptSubmit",
    "PreCompact",
    "Setup",
    "Stop",
}


def test_hooks_json_dispatch_consistency():
    manifest = json.loads(_read("hooks/hooks.json"))["hooks"]
    assert set(manifest) <= _KNOWN_EVENTS, f"unknown hook event: {set(manifest) - _KNOWN_EVENTS}"

    dispatched = set()
    for entries in manifest.values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["type"] == "command"
                m = re.search(r"run-hook\"\s+([a-z-]+)", hook["command"])
                if m:
                    dispatched.add(m.group(1))
                else:
                    # Non run-hook entries must point at a bundled bin launcher.
                    b = re.search(r"bin/([a-z-]+)\"", hook["command"])
                    assert b, f"unrecognized hook command: {hook['command']}"
                    assert b.group(1) in cli.COMMANDS
                    assert (REPO_ROOT / "bin" / b.group(1)).is_file()
    assert dispatched == set(cli.HOOKS), (
        "hooks.json dispatch names and cli.HOOKS have drifted apart: "
        f"manifest-only={dispatched - set(cli.HOOKS)}, code-only={set(cli.HOOKS) - dispatched}"
    )


def test_bin_launchers_match_cli_commands():
    bins = {p.name for p in (REPO_ROOT / "bin").iterdir() if p.is_file()}
    assert bins == set(cli.COMMANDS)


def test_dispatcher_modules_resolve():
    import importlib

    for mod, attr in list(cli.HOOKS.values()) + list(cli.COMMANDS.values()):
        assert hasattr(importlib.import_module(mod), attr)


# --- template placeholder contracts ------------------------------------------

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")


def test_claude_md_template_placeholders():
    # Must match exactly what init.py:_write_claude_md substitutes.
    expected = {"IMPORTS", "PLAN_DIR", "PROJECT_TYPE", "LINE_BUDGET"}
    for lang in ("en", "zh"):
        found = set(_PLACEHOLDER.findall(_read(f"templates/claude-md-template.{lang}.md")))
        assert found == expected, f"{lang} template placeholders {found} != {expected}"


def test_plan_template_placeholders():
    # Must match exactly what pre_edit.py scaffolding substitutes.
    expected = {"TITLE", "STATUS_FIELD", "DATE", "TIMESTAMP", "REL_PATH", "SOURCE"}
    found = set(_PLACEHOLDER.findall(_read("templates/plan-template.md")))
    assert found == expected


def test_claude_md_templates_within_budget():
    # Rendered output adds at most 2 lines (@AGENTS.md import); the godot
    # claude-md-budget gate blocks at 120 lines, so keep the template ≤ 110
    # to leave the user real headroom.
    for lang in ("en", "zh"):
        n = len(_read(f"templates/claude-md-template.{lang}.md").splitlines())
        assert n <= 110, f"{lang} template is {n} lines — shrink it, knowledge belongs in docs/"


# --- config presets ------------------------------------------------------------


def _presets() -> dict[str, dict]:
    from harness.commands.init import CUSTOM_CONFIG

    return {
        "godot": json.loads(_read("templates/godot/config.json")),
        "web": json.loads(_read("templates/web/config.json")),
        "custom": json.loads(CUSTOM_CONFIG),
    }


def test_config_presets_parse_and_conform():
    schema_props = set(json.loads(_read("templates/config.schema.json"))["properties"])
    for name, cfg in _presets().items():
        assert set(cfg) <= schema_props, f"{name}: unknown config keys {set(cfg) - schema_props}"
        for gate in cfg.get("gates", []):
            assert isinstance(gate.get("name"), str) and gate["name"], f"{name}: gate missing name"
            assert isinstance(gate.get("command"), str) and gate["command"]
        glob = cfg.get("plan", {}).get("codeGlob", "")
        re.compile(glob)  # must be a valid regex (may be empty)
        assert cfg.get("loopDetection", {}).get("threshold", 1) >= 1


def test_config_presets_have_claude_md_budget_gate():
    # init scaffolds a CLAUDE.md, so every preset must carry the budget gate,
    # and it must tolerate a missing file (--no-claude-md projects).
    for name, cfg in _presets().items():
        gates = {g["name"]: g for g in cfg.get("gates", [])}
        assert "claude-md-budget" in gates, f"{name}: claude-md-budget gate missing"
        assert "test ! -f CLAUDE.md ||" in gates["claude-md-budget"]["command"], (
            f"{name}: claude-md-budget must tolerate a missing CLAUDE.md"
        )


def test_config_presets_validate_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_read("templates/config.schema.json"))
    for name, cfg in _presets().items():
        jsonschema.validate(cfg, schema)


# --- plugin manifest -----------------------------------------------------------


def test_version_consistency():
    plugin = json.loads(_read(".claude-plugin/plugin.json"))
    marketplace = json.loads(_read(".claude-plugin/marketplace.json"))
    assert plugin["version"] == marketplace["version"]
    badge = f"version-{plugin['version']}-"
    for readme in ("README.md", "README.en.md"):
        assert badge in _read(readme), f"{readme} version badge != {plugin['version']}"


def test_optional_auto_eval_manifest():
    manifest = json.loads(_read("hooks/optional-auto-eval.json"))
    stop = manifest["hooks"]["Stop"][0]["hooks"][0]
    assert stop["type"] == "agent"
    assert stop["once"] is True, "auto-eval agent hook must be once:true (runs every Stop otherwise)"


def test_evaluator_agent_cannot_edit():
    head = _read("agents/evaluator.md").split("---")[1]
    m = re.search(r"^disallowedTools:\s*(.+)$", head, re.M)
    assert m, "evaluator.md frontmatter must declare disallowedTools"
    tools = {t.strip() for t in m.group(1).split(",")}
    assert {"Write", "Edit", "MultiEdit", "NotebookEdit"} <= tools, (
        "Generator/Evaluator separation requires the evaluator to be edit-less"
    )
