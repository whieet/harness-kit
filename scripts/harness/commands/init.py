"""harness-init — deterministic scaffolder for .harness/config.json + skeleton.

Cross-platform: writes the git pre-commit hook with
a forward-slash $BIN_DIR fallback (the in-repo hook is a bash script — Git on
Windows ships bash and uses it to run repo hooks too).
"""
from __future__ import annotations

import os
import shutil
import sys

from .. import gitutil, util
from ..context import HarnessContext, load_context

CUSTOM_CONFIG = """\
{
  "projectType": "custom",
  "verificationMode": "strict",
  "gates": [
    { "name": "claude-md-budget", "command": "test ! -f CLAUDE.md || test \\"$(wc -l < CLAUDE.md)\\" -le 200 || { echo 'CLAUDE.md exceeds 200 lines — move detail into docs/'; exit 1; }", "blocking": false },
    { "name": "doc-links", "command": "harness-doc-links", "blocking": true },
    { "name": "plan-dod", "command": "harness-check-plan-dod", "blocking": true }
  ],
  "layeringRules": [],
  "plan": { "dir": "docs/plans", "codeGlob": "", "statusField": "status", "completedValue": "completed", "checklistRegex": "^- \\\\[ \\\\]" },
  "docs": { "scanRoots": ["docs"] },
  "metrics": [ { "name": "completed", "glob": "docs/plans/completed/*.md", "exclude": "gitkeep" } ],
  "phases": [ { "name": "Phase 0 — Bootstrap", "when": [], "capabilities": ["base gates"] } ],
  "loopDetection": { "threshold": 5 },
  "evaluator": { "enabled": false }
}
"""


def _plugin_root() -> str:
    env = os.environ.get("HARNESS_KIT_ROOT")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _bin_dir() -> str:
    return os.path.join(_plugin_root(), "bin")


def _detect_type(project: str) -> str | None:
    if os.path.isfile(os.path.join(project, "project.godot")):
        return "godot"
    if os.path.isfile(os.path.join(project, "package.json")):
        return "web"
    return None


def _to_posix(path: str) -> str:
    """Bash on Git-Bash accepts forward slashes; PowerShell prefers backslashes,
    but the pre-commit hook IS bash, so use forward slashes everywhere."""
    return path.replace("\\", "/")


def _write_config(ctx: HarnessContext, ttype: str, force: bool, tpl_root: str) -> None:
    cfg = os.path.join(ctx.harness_dir, "config.json")
    if os.path.isfile(cfg) and not force:
        print("  .harness/config.json exists — keeping (use --force to reset)")
        return
    if ttype == "custom":
        util.write_text(cfg, CUSTOM_CONFIG)
        print("  wrote .harness/config.json (custom skeleton — edit gates/layeringRules for your stack)")
        return
    src = os.path.join(tpl_root, ttype, "config.json")
    if not os.path.isfile(src):
        print("  WARN: template missing: %s" % src)
        return
    shutil.copyfile(src, cfg)
    print(f"  wrote .harness/config.json ({ttype} preset)")


def _write_rubric(ctx: HarnessContext, ttype: str, force: bool, tpl_root: str) -> None:
    src = os.path.join(tpl_root, ttype, "rubric.md")
    if not os.path.isfile(src):
        return
    dst = os.path.join(ctx.harness_dir, "rubric.md")
    if os.path.isfile(dst) and not force:
        print("  .harness/rubric.md exists — keeping")
        return
    shutil.copyfile(src, dst)
    print("  wrote .harness/rubric.md")


def _scaffold_plan_dirs(ctx: HarnessContext, tpl_root: str) -> None:
    # Reload after writing the config so plan.dir is honored.
    ctx.reload_config()
    plan_dir = ctx.cfg_get_str("plan.dir", "docs/plans")
    for sub in ("active", "completed"):
        full = os.path.join(ctx.project_dir, plan_dir, sub)
        os.makedirs(full, exist_ok=True)
        kp = os.path.join(full, ".gitkeep")
        if not os.path.isfile(kp):
            open(kp, "a", encoding="utf-8").close()
    tpl_src = os.path.join(tpl_root, "plan-template.md")
    tpl_dst = os.path.join(ctx.project_dir, plan_dir, "_template.md")
    if os.path.isfile(tpl_src) and not os.path.isfile(tpl_dst):
        try:
            shutil.copyfile(tpl_src, tpl_dst)
        except OSError:
            pass
    print(f"  plan dirs: {plan_dir}/{{active,completed}}")


# Mirrors the per-preset claude-md-budget gate thresholds (templates/*/config.json).
_CLAUDE_MD_BUDGETS = {"godot": "120", "web": "200", "custom": "200"}


def _write_claude_md(ctx: HarnessContext, ttype: str, lang: str, enabled: bool, tpl_root: str) -> None:
    if not enabled:
        print("  CLAUDE.md skipped (--no-claude-md)")
        return
    dst = os.path.join(ctx.project_dir, "CLAUDE.md")
    nested = os.path.join(ctx.project_dir, ".claude", "CLAUDE.md")
    if os.path.isfile(dst) or os.path.isfile(nested):
        print("  CLAUDE.md exists — keeping (user-owned; not affected by --force)")
        return
    src = os.path.join(tpl_root, f"claude-md-template.{lang}.md")
    if not os.path.isfile(src):
        print("  WARN: template missing: %s" % src)
        return
    tpl = util.safe_read(src)
    has_agents_md = os.path.isfile(os.path.join(ctx.project_dir, "AGENTS.md"))
    for k, v in (
        ("PLAN_DIR", ctx.cfg_get_str("plan.dir", "docs/plans")),
        ("PROJECT_TYPE", ttype),
        ("LINE_BUDGET", _CLAUDE_MD_BUDGETS.get(ttype, "200")),
        ("IMPORTS", "@AGENTS.md\n\n" if has_agents_md else ""),
    ):
        tpl = tpl.replace("{{%s}}" % k, v)
    util.write_text(dst, tpl)
    print("  wrote CLAUDE.md (harness constitution — fill in the project-specific sections)")


def _write_state_gitignore(ctx: HarnessContext) -> None:
    util.write_text(os.path.join(ctx.harness_dir, ".gitignore"), "state/\n")


def _write_precommit(ctx: HarnessContext) -> None:
    hooks_dir = os.path.join(ctx.harness_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    bin_dir_posix = _to_posix(_bin_dir())
    body = (
        "#!/usr/bin/env bash\n"
        "# harness-kit VCS gate — runs the same verify orchestrator before each commit.\n"
        "# Tries PATH first (works inside Claude Code), falls back to the plugin path baked\n"
        "# at init time. If the plugin moved/updated, re-run: /harness-kit:init --force\n"
        "if command -v harness-verify >/dev/null 2>&1; then exec harness-verify; fi\n"
        f'exec "{bin_dir_posix}/harness-verify"\n'
    )
    pc = os.path.join(hooks_dir, "pre-commit")
    util.write_text(pc, body)
    util.chmod_x(pc)
    if gitutil.is_inside_worktree(ctx.project_dir):
        if gitutil.set_hooks_path(".harness/hooks", ctx.project_dir):
            print("  git core.hooksPath -> .harness/hooks")


def run(argv: list[str]) -> int:
    force = False
    claude_md = True
    lang = "en"
    ttype: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--force":
            force = True
        elif a == "--no-claude-md":
            claude_md = False
        elif a == "--lang":
            if i + 1 >= len(argv):
                print("harness-init: --lang requires a value (en|zh)")
                return 2
            i += 1
            lang = argv[i]
        elif a.startswith("--lang="):
            lang = a.split("=", 1)[1]
        elif a in ("godot", "web", "custom"):
            ttype = a
        else:
            # Emit to stdout so log scrapers can pick up unknown-arg notices.
            print(f"harness-init: unknown arg '{a}'")
            return 2
        i += 1
    if lang not in ("en", "zh"):
        print(f"harness-init: unsupported --lang '{lang}' (expected en|zh)")
        return 2

    ctx = load_context("")
    project = ctx.project_dir
    try:
        os.chdir(project)
    except OSError:
        print("harness-init: cannot cd to project root")
        return 1

    if ttype is None:
        detected = _detect_type(project)
        if detected is None:
            print("harness-init: could not auto-detect project type. Pass godot|web|custom.")
            return 2
        ttype = detected

    print(f"harness-init: project={project} type={ttype}")
    os.makedirs(ctx.harness_dir, exist_ok=True)

    tpl_root = os.path.join(_plugin_root(), "templates")
    _write_config(ctx, ttype, force, tpl_root)
    _write_rubric(ctx, ttype, force, tpl_root)
    _scaffold_plan_dirs(ctx, tpl_root)
    _write_claude_md(ctx, ttype, lang, claude_md, tpl_root)
    _write_state_gitignore(ctx)
    _write_precommit(ctx)
    print(f"  ✓ harness-kit initialized ({ttype}). Next: /harness-kit:verify")
    return 0
