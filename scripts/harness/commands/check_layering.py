"""harness-check-layering — config-driven dependency-direction linter."""
from __future__ import annotations

import glob
import os
import re
import sys

from .. import util
from ..context import load_context


def run(argv: list[str]) -> int:
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0

    rules = ctx.config.get("layeringRules") or []
    if not rules:
        print("  ✓ layering: no rules configured")
        return 0

    fail = 0
    for r in rules:
        if not isinstance(r, dict):
            continue
        scope = r.get("scope", "")
        forbidden = r.get("forbidden", "")
        msg = r.get("message", "")
        if not scope or not forbidden:
            continue
        try:
            pat = re.compile(forbidden)
        except re.error as e:
            print(f"  ✗ invalid forbidden regex {forbidden!r}: {e}")
            fail = 1
            continue
        for path in sorted(glob.glob(scope, recursive=True)):
            if not os.path.isfile(path):
                continue
            text = util.safe_read(path)
            for n, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    print(f"  ✗ {path}:{n}  {msg}")
                    fail = 1
                    break  # one report per file is enough

    if fail:
        print("  → fix the dependency direction above.")
        return 1
    print("  ✓ layering OK")
    return 0
