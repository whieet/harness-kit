"""harness-doc-gardening — config-driven doc/code coherence scan."""
from __future__ import annotations

import datetime
import glob
import os
import re

from .. import util
from ..context import load_context


def _add(issues: list[tuple[str, str]], check: str, detail: str) -> None:
    issues.append((check, detail))


def run(argv: list[str]) -> int:
    ctx = load_context("")
    try:
        os.chdir(ctx.project_dir)
    except OSError:
        return 0

    cfg = ctx.config
    plan = cfg.get("plan") or {}
    docs = cfg.get("docs") or {}
    issues: list[tuple[str, str]] = []

    plan_dir = plan.get("dir", "docs/plans")
    completed_dir = os.path.join(plan_dir, "completed")

    # 1. completed-plan status consistency
    status_field = plan.get("statusField")
    completed_val = plan.get("completedValue", "completed")
    if status_field and os.path.isdir(completed_dir):
        sline = re.compile(re.escape(status_field) + r"\**\s*[：:]\s*(.+?)\s*$")
        for p in sorted(glob.glob(os.path.join(completed_dir, "*.md"))):
            if os.path.basename(p) == ".gitkeep":
                continue
            st = None
            for ln in util.safe_read(p).splitlines():
                m = sline.search(ln)
                if m:
                    st = m.group(1).strip().strip("*").strip()
                    break
            if st and st != completed_val:
                _add(issues, "status-mismatch", f"{os.path.basename(p)}: in completed/ but status='{st}'")

    # 2. template compliance for completed plans
    required = plan.get("requiredFields") or []
    if required and os.path.isdir(completed_dir):
        for p in sorted(glob.glob(os.path.join(completed_dir, "*.md"))):
            if os.path.basename(p) == ".gitkeep":
                continue
            text = util.safe_read(p)
            for field in required:
                if field not in text:
                    _add(issues, "template-field", f"{os.path.basename(p)}: missing '{field}'")

    # 3. placeholder content
    patterns = docs.get("placeholderPatterns") or [
        "TODO: fill",
        "待补充",
        "暂未填充",
        "当前为占位",
        "本文档应包含",
    ]
    scan_roots = docs.get("scanRoots") or ["docs"]
    seen: set[str] = set()
    for root in scan_roots:
        if root == ".":
            candidates = glob.glob("*.md")
        else:
            candidates = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
        for p in candidates:
            if p in seen or not os.path.isfile(p):
                continue
            if os.path.basename(p) == "_template.md":
                continue
            seen.add(p)
            text = util.safe_read(p)
            for pat in patterns:
                if pat in text:
                    _add(issues, "placeholder", f"{p}: contains '{pat}'")
                    break

    # 4. quality-doc staleness
    qpath = docs.get("qualityPath")
    try:
        stale_days = int(docs.get("stalenessDays", 14))
    except (TypeError, ValueError):
        stale_days = 14
    if qpath and os.path.isfile(qpath):
        today = datetime.date.today()
        qtext = util.safe_read(qpath)
        flagged = 0
        for line in qtext.splitlines():
            if "|" not in line:
                continue
            m = re.search(r"\d{4}-\d{2}-\d{2}", line)
            if not m:
                continue
            try:
                d = datetime.date.fromisoformat(m.group(0))
            except ValueError:
                continue
            age = (today - d).days
            if age > stale_days:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                label = cells[0] if cells else "(row)"
                _add(
                    issues,
                    "stale-quality",
                    f"{os.path.basename(qpath)} row '{label}': {m.group(0)} is {age} days old (> {stale_days})",
                )
                flagged += 1
        if flagged == 0:
            dates = []
            for ds in re.findall(r"\d{4}-\d{2}-\d{2}", qtext):
                try:
                    dates.append(datetime.date.fromisoformat(ds))
                except ValueError:
                    pass
            if dates:
                newest = max(dates)
                age = (today - newest).days
                if age > stale_days:
                    _add(
                        issues,
                        "stale-quality",
                        f"{os.path.basename(qpath)}: newest dated entry {newest} is {age} days old (> {stale_days})",
                    )

    # 5. architecture drift
    apath = docs.get("architecturePath")
    layer_re = docs.get("layerPathRegex")
    if apath and layer_re and os.path.isfile(apath):
        arch_text = util.safe_read(apath)
        try:
            refs = set(re.findall(layer_re, arch_text))
        except re.error:
            refs = set()
        for ref in sorted(refs):
            if not os.path.exists(ref):
                _add(issues, "arch-drift", f"{os.path.basename(apath)} declares '{ref}' which does not exist on disk")
        base = docs.get("layerBaseDir")
        ignore_dirs = set(docs.get("layerIgnoreDirs") or [])
        if base and os.path.isdir(base):
            for entry in sorted(os.listdir(base)):
                full = os.path.join(base, entry)
                if (
                    not os.path.isdir(full)
                    or entry in ignore_dirs
                    or entry.startswith(".")
                ):
                    continue
                if full not in arch_text and full not in refs:
                    _add(issues, "arch-drift", f"{full} exists but is not declared in {os.path.basename(apath)} (undeclared layer)")

    # 6. file naming convention
    nglob = docs.get("namingGlob")
    ndisallow = docs.get("namingDisallow")
    if nglob and ndisallow:
        try:
            rx = re.compile(ndisallow)
        except re.error:
            rx = None
        if rx is not None:
            for p in glob.glob(nglob, recursive=True):
                if not os.path.isfile(p):
                    continue
                base = os.path.splitext(os.path.basename(p))[0]
                if rx.search(base):
                    _add(issues, "naming", f"{p}: violates naming rule")

    if not issues:
        print("  ✓ doc-gardening: no drift")
        return 0
    print(f"  doc-gardening findings ({len(issues)}):")
    for check, detail in issues:
        print(f"    [{check}] {detail}")
    return 1
