"""harness-doc-links — markdown dead-link checker.

Resolves relative `[text](path#anchor)` links against the filesystem.
Top-level *.md is always scanned; configured scanRoots are recursive.
"""
from __future__ import annotations

import os
import re
import sys

from .. import util
from ..context import load_context

# sed -E 's/^([0-9]+):.*\[[^]]+\]\(([^)]+)\).*/\1\t\2/' in the original bash
# is GREEDY: the leading `.*` consumes as much as possible, so only the LAST
# [..](..) on each line is captured. We replicate that here so existing
# projects that pass the old gate continue to pass the new one — even when a
# line contains multiple links (common in tables).
LINK_RE_LAST = re.compile(r"^.*\[[^\]]+\]\(([^)]+)\)")


def _md_under(root: str, recursive: bool) -> list[str]:
    out: list[str] = []
    if not os.path.isdir(root):
        return out
    if recursive:
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if fn.endswith(".md"):
                    out.append(os.path.join(dirpath, fn))
    else:
        for fn in os.listdir(root):
            full = os.path.join(root, fn)
            if fn.endswith(".md") and os.path.isfile(full):
                out.append(full)
    return out


def run(argv: list[str]) -> int:
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0

    docs_cfg = ctx.config.get("docs") or {}
    roots = docs_cfg.get("scanRoots") or ["docs"]

    files = set(_md_under(".", recursive=False))
    for r in roots:
        if not isinstance(r, str) or not r or r == ".":
            continue
        for f in _md_under(r, recursive=True):
            files.add(f)
    sorted_files = sorted(files)

    fail = 0
    for f in sorted_files:
        directory = os.path.dirname(f) or "."
        text = util.safe_read(f)
        for lineno, line in enumerate(text.splitlines(), 1):
            m = LINK_RE_LAST.match(line)
            if not m:
                continue
            target = m.group(1)  # raw — bash's sed extraction did not strip
            if not target:
                continue
            # URL skip: case-sensitive prefix match, matching the bash
            # `case ... in http*|"#"*|"mailto:"*)` glob.
            if (
                target.startswith("http")
                or target.startswith("#")
                or target.startswith("mailto:")
            ):
                continue
            file_part = target.split("#", 1)[0]
            if not file_part:
                continue
            full = os.path.join(directory, file_part)
            if not os.path.exists(full):
                sys.stderr.write(f"  ✗ {f}:{lineno}  → dead link: {target}\n")
                fail = 1

    if fail:
        return 1
    print("  ✓ doc links OK")
    return 0
