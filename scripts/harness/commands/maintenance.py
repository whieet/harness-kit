"""harness-maintenance — Setup(maintenance) hook + manual repair tool."""
from __future__ import annotations

import json
import os

from .. import util
from ..context import load_context, read_stdin


def run(argv: list[str]) -> int:
    stdin_raw = read_stdin()
    ctx = load_context(stdin_raw)
    if not ctx.has_config():
        print("harness-maintenance: no .harness/config.json — run /harness-kit:init first.")
        return 0
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0

    try:
        with open(ctx.config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"harness-maintenance: .harness/config.json is INVALID JSON: {e}")
        return 0

    changed: list[str] = []
    if "phases" in cfg:
        del cfg["phases"]
        changed.append("removed legacy phases[] (maturity auto-router retired)")
    if "enabledCapabilities" not in cfg:
        cfg["enabledCapabilities"] = {
            "planGate": True,
            "loopDetection": True,
            "toolTrace": True,
            "evaluator": True,
            "contextSnapshot": True,
            "evaluatorAutoDispatch": False,
        }
        changed.append("added enabledCapabilities{} defaults")
    if "effortRouting" not in cfg:
        cfg["effortRouting"] = {"enabled": False}
        changed.append("added effortRouting{enabled:false}")

    warns: list[str] = []
    if not isinstance(cfg.get("gates", []), list):
        warns.append("gates is not a list")

    if changed:
        with open(ctx.config_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print("harness-maintenance: migrated .harness/config.json:")
        for c in changed:
            print("  - " + c)
    else:
        print("harness-maintenance: config already up to date.")
    for w in warns:
        print("  WARN: " + w)

    # scaffold state dir + gitignore
    os.makedirs(ctx.state_dir(), exist_ok=True)
    gi = os.path.join(ctx.harness_dir, ".gitignore")
    if not os.path.isfile(gi):
        util.write_text(gi, "state/\n")
    print("harness-maintenance: state dir + .gitignore ok")
    return 0
