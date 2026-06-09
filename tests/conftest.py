"""tests/conftest.py — pytest setup.

Adds the repo root to sys.path so tests can `from tests._helpers import ...`.
Also exports an `old_plugin_root` fixture that builds a checkout of HEAD's bash
scripts in a tmpdir; parity tests run the old `bash bin/*` and `bash scripts/on-*.sh`
against this checkout, then run the new Python against the live tree, and diff.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))  # so `from harness import ...` works in-process


@pytest.fixture(scope="session")
def old_plugin_root(tmp_path_factory) -> Path:
    """Materialize the HEAD version of the plugin (the pre-port bash scripts)
    into a tmpdir so parity tests can invoke them while the live tree contains
    the new Python implementation.
    """
    out = tmp_path_factory.mktemp("old-plugin")
    # `git archive HEAD | tar -x -C out` is the cleanest way to get a worktree
    # of HEAD without polluting working dir.
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", "HEAD"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(out)],
        input=archive.stdout,
        check=True,
    )
    # Make sure scripts have +x.
    for p in (out / "bin").iterdir():
        os.chmod(p, 0o755)
    for p in (out / "scripts").glob("*.sh"):
        os.chmod(p, 0o755)
    return out
