"""D7: Property-based parity — fuzz inputs, assert old bash and new Python agree.

Generates random-but-valid hook payloads and config files, runs both
implementations against the same fixture, and asserts identical behavior
(exit code + normalized output). This is the strongest "100% equivalent"
evidence: any divergence found here is a real regression.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import REPO_ROOT, make_project

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="needs Unix tools for the old impl"
)


ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
MIN_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
HMS_RE = re.compile(r"\d{6}")
# git short-hash (7+ hex chars) appears in `git log --oneline` output; differs
# between independently-init'd repos because commit hashes include timestamps.
# Use lookaround instead of \b — \b sees `n` and `9` both as word chars so
# `\bHASH\b` fails when the hash is preceded by `\n` literal (a backslash + n)
# in a JSON-escaped string.
GIT_SHORT_HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7,40}(?![0-9a-fA-F])")


def _normalize(s: str, proj: Path | None = None) -> str:
    if proj:
        s = s.replace(str(proj), "<PROJ>")
    s = ISO_TS_RE.sub("<ISO>", s)
    s = MIN_RE.sub("<MIN>", s)
    # auto-<DATE>-<HMS>-<slug>.md plan filenames embed time-of-day (HHMMSS);
    # if old and new runs cross a second boundary the HMS differs. Also
    # session_id "s0" etc. can collide with date digits — apply after MIN_RE.
    s = re.sub(r"auto-\d{4}-\d{2}-\d{2}-\d{6}-", "auto-<TS>-", s)
    s = GIT_SHORT_HASH_RE.sub("<HASH>", s)
    return s


def _run_old(old: Path, kind: str, name: str, proj: Path, stdin: str = "", args=None):
    """kind ∈ {hook, bin}."""
    path = old / "scripts" / name if kind == "hook" else old / "bin" / name
    return subprocess.run(
        ["bash", str(path), *(args or [])],
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj)},
        check=False,
    )


def _run_new(kind: str, name_or_dispatch: str, proj: Path, stdin: str = "", args=None):
    env = os.environ.copy()
    env["HARNESS_KIT_ROOT"] = str(REPO_ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    if kind == "hook":
        cmd = ["bash", str(REPO_ROOT / "scripts" / "run-hook"), name_or_dispatch]
    else:
        cmd = ["bash", str(REPO_ROOT / "bin" / name_or_dispatch)]
    return subprocess.run(
        cmd + (args or []),
        cwd=str(proj),
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _assert_parity(old_r, new_r, *, proj=None, ctx: str = ""):
    """Assert old and new implementations produced equivalent results."""
    assert old_r.returncode == new_r.returncode, (
        f"{ctx}: rc differs old={old_r.returncode} new={new_r.returncode}\n"
        f"OLD stdout: {old_r.stdout[:300]!r}\n"
        f"NEW stdout: {new_r.stdout[:300]!r}\n"
        f"OLD stderr: {old_r.stderr[:300]!r}\n"
        f"NEW stderr: {new_r.stderr[:300]!r}"
    )
    old_o = _normalize(old_r.stdout, proj)
    new_o = _normalize(new_r.stdout, proj)
    old_e = _normalize(old_r.stderr, proj)
    new_e = _normalize(new_r.stderr, proj)
    assert old_o == new_o, f"{ctx}: stdout differs\n--- old ---\n{old_o}\n--- new ---\n{new_o}"
    assert old_e == new_e, f"{ctx}: stderr differs\n--- old ---\n{old_e}\n--- new ---\n{new_e}"


# ---------- random payload generators ---------------------------------------


def _random_payload(seed: int, proj: Path) -> str:
    """Generate a varied but valid hook payload."""
    rng = random.Random(seed)
    payload = {"cwd": str(proj)}
    if rng.random() < 0.5:
        payload["session_id"] = rng.choice(["a", "b", "default", f"s{seed}"])
    if rng.random() < 0.5:
        payload["tool_name"] = rng.choice(["Edit", "Write", "Bash", "Read", "Grep"])
    if rng.random() < 0.5:
        payload["tool_input"] = {
            "file_path": rng.choice([
                str(proj / "x.py"),
                str(proj / "src" / "y.py"),
                str(proj / "docs" / "z.md"),
                "/etc/hosts",
            ]),
        }
    if rng.random() < 0.3:
        payload["exit_code"] = rng.choice([0, 1, 2, 127])
    if rng.random() < 0.3:
        payload["error_message"] = "test error " + str(seed)
    return json.dumps(payload)


# ---------- 10 fuzz seeds × 8 hooks = 80 parity assertions -----------------


@pytest.mark.parametrize("seed", list(range(10)))
@pytest.mark.parametrize("script,dispatch", [
    ("on-session-start.sh", "session-start"),
    ("on-user-prompt.sh", "user-prompt"),
    ("on-pre-edit.sh", "pre-edit"),
    ("on-post-edit.sh", "post-edit"),
    ("on-pre-compact.sh", "pre-compact"),
    ("on-post-tool.sh", "post-tool"),
    ("on-tool-failure.sh", "tool-failure"),
    ("on-stop-verify.sh", "stop-verify"),
])
def test_hook_parity_random_payload(old_plugin_root, tmp_path, seed, script, dispatch):
    """For each (hook × seed), bash and python must produce equivalent output."""
    proj_o = make_project(tmp_path / "old", extra_config={"plan": {"codeGlob": r"\.py$"}})
    proj_n = make_project(tmp_path / "new", extra_config={"plan": {"codeGlob": r"\.py$"}})
    payload_o = _random_payload(seed, proj_o)
    payload_n = _random_payload(seed, proj_n).replace(str(proj_o), str(proj_n))
    o = _run_old(old_plugin_root, "hook", script, proj_o, stdin=payload_o)
    n = _run_new("hook", dispatch, proj_n, stdin=payload_n)
    _assert_parity(o, n, proj=None, ctx=f"{dispatch} seed={seed}")


# ---------- 10 random configs × verify ------------------------------------


def _random_config_gates(seed: int) -> list:
    rng = random.Random(seed)
    n = rng.randint(0, 5)
    out = []
    for i in range(n):
        kind = rng.choice(["pass", "fail", "soft-fail", "skip-proc"])
        if kind == "pass":
            out.append({"name": f"g{i}-ok", "command": "true", "blocking": True})
        elif kind == "fail":
            out.append({"name": f"g{i}-fail", "command": "echo bad >&2; exit 1", "blocking": True})
        elif kind == "soft-fail":
            out.append({"name": f"g{i}-soft", "command": "echo warn; exit 1", "blocking": False})
        else:
            # skipWhenProcess with an unlikely string
            out.append({"name": f"g{i}-skip", "command": "true", "blocking": True,
                       "skipWhenProcess": f"definitely-not-running-{i}"})
    return out


@pytest.mark.parametrize("seed", list(range(10)))
def test_verify_parity_random_gates(old_plugin_root, tmp_path, seed):
    """Random gate compositions → bash and python must report same outcome."""
    extra = {"gates": _random_config_gates(seed)}
    proj_o = make_project(tmp_path / "old", extra_config=extra)
    proj_n = make_project(tmp_path / "new", extra_config=extra)
    o = _run_old(old_plugin_root, "bin", "harness-verify", proj_o)
    n = _run_new("bin", "harness-verify", proj_n)
    _assert_parity(o, n, proj=None, ctx=f"verify seed={seed} gates={len(extra['gates'])}")


# ---------- 5 random doc-link fixtures × parity ----------------------------


@pytest.mark.parametrize("seed", list(range(5)))
def test_doc_links_parity_random_docs(old_plugin_root, tmp_path, seed):
    rng = random.Random(seed)
    extra = {"docs": {"scanRoots": ["docs"]}}
    proj_o = make_project(tmp_path / "old", extra_config=extra)
    proj_n = make_project(tmp_path / "new", extra_config=extra)
    for proj in (proj_o, proj_n):
        d = proj / "docs"
        d.mkdir(exist_ok=True)
        # 3 markdown files; each has a random mix of live/dead/url links
        live = d / "live.md"
        live.write_text("alive\n")
        rng_local = random.Random(seed)
        for fname in ("a.md", "b.md", "c.md"):
            lines = []
            for _ in range(rng_local.randint(1, 5)):
                kind = rng_local.choice(["live", "dead", "url", "anchor", "multi"])
                if kind == "live":
                    lines.append("- see [x](live.md)")
                elif kind == "dead":
                    lines.append("- see [x](missing.md)")
                elif kind == "url":
                    lines.append("- see [x](https://example.com)")
                elif kind == "anchor":
                    lines.append("- see [x](#section)")
                else:
                    # multi: two links on one line — bash picks the LAST one
                    lines.append("- see [a](missing.md) and [b](live.md)")
            (d / fname).write_text("\n".join(lines) + "\n")
    o = _run_old(old_plugin_root, "bin", "harness-doc-links", proj_o)
    n = _run_new("bin", "harness-doc-links", proj_n)
    _assert_parity(o, n, proj=None, ctx=f"doc-links seed={seed}")


# ---------- 5 random layering-rule fixtures × parity ------------------------


@pytest.mark.parametrize("seed", list(range(5)))
def test_layering_parity_random_rules(old_plugin_root, tmp_path, seed):
    extra = {"layeringRules": [
        {"scope": "src/ui/**/*.py", "forbidden": "import db", "message": "UI must not import db"},
        {"scope": "src/domain/**/*.py", "forbidden": "import flask", "message": "domain pure"},
    ]}
    proj_o = make_project(tmp_path / "old", extra_config=extra)
    proj_n = make_project(tmp_path / "new", extra_config=extra)
    for proj in (proj_o, proj_n):
        rng = random.Random(seed)  # re-seed per project so file sets agree
        for d, fname, content in [
            ("src/ui", "good.py", "x = 1\n"),
            ("src/ui", "bad.py", "import db\n"),
            ("src/domain", "ok.py", "x = 1\n"),
            ("src/domain", "bad.py", "import flask\n"),
        ]:
            (proj / d).mkdir(parents=True, exist_ok=True)
            if rng.random() < 0.7:  # randomly include the file
                (proj / d / fname).write_text(content)
    o = _run_old(old_plugin_root, "bin", "harness-check-layering", proj_o)
    n = _run_new("bin", "harness-check-layering", proj_n)
    _assert_parity(o, n, proj=None, ctx=f"layering seed={seed}")
