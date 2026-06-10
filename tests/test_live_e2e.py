"""Live e2e — drives a REAL headless Claude Code instance via scripts/dev-e2e.sh.

Triple-gated so `pytest tests` stays free by default:
  1. @pytest.mark.live marker (deselect with -m "not live")
  2. requires the `claude` CLI on PATH
  3. requires explicit opt-in via HARNESS_LIVE_E2E=1

Run it on purpose:
  HARNESS_LIVE_E2E=1 python3 -m pytest tests/test_live_e2e.py -v -s
Or skip pytest and use the script directly: bash scripts/dev-e2e.sh full
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from tests._helpers import REPO_ROOT

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not shutil.which("claude"), reason="claude CLI not on PATH"),
    pytest.mark.skipif(
        os.environ.get("HARNESS_LIVE_E2E") != "1",
        reason="live e2e is opt-in: set HARNESS_LIVE_E2E=1 (drives a real Claude, consumes tokens)"),
]


def _dev_e2e(*args: str, out_dir: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["E2E_OUT_DIR"] = out_dir
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "dev-e2e.sh"), *args],
        capture_output=True, text=True, env=env, check=False,
        encoding="utf-8", errors="replace")


def _skip_if_inconclusive(r: subprocess.CompletedProcess) -> None:
    if r.returncode == 3:
        pytest.skip("live run rate-limited upstream — inconclusive, re-run later")


def test_probe(tmp_path):
    r = _dev_e2e("probe", out_dir=str(tmp_path))
    _skip_if_inconclusive(r)
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert (tmp_path / "evidence-probe.json").is_file()


def test_full_with_audit(tmp_path):
    r = _dev_e2e("full", out_dir=str(tmp_path))
    _skip_if_inconclusive(r)
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert (tmp_path / "evidence.json").is_file()
    assert (tmp_path / "audit.json").is_file()
