"""tests/conftest.py — pytest setup.

Adds the repo root to sys.path so tests can `from tests._helpers import ...`.

Also exports an `old_plugin_root` session-scoped fixture that materializes the
pre-port bash implementation into a tmpdir. Parity tests run the original
`bash bin/*` and `bash scripts/on-*.sh` from this checkout against fresh
fixtures, run the new Python against the live tree on identical fixtures,
and assert equivalent stdout/stderr/exit-code.

To survive the merge that retired the old .sh files, we DON'T use `git
archive HEAD` — HEAD no longer contains them. Instead we walk history and
pick the last commit whose tree still has `scripts/on-pre-edit.sh`. That
commit (the pre-port baseline) becomes the parity oracle forever after.

If no such commit is reachable (e.g. a shallow clone with depth=1 in CI),
the fixture is marked skipped — every parity test then auto-skips, while
the cross-platform smoke / d1 / d3 / d7 / d9 suites continue to run.
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


def pytest_configure(config):
    # No pytest.ini/pyproject in this repo — markers are registered here.
    config.addinivalue_line(
        "markers",
        "live: drives a real headless Claude Code instance (needs `claude` CLI + auth; "
        "opt-in via HARNESS_LIVE_E2E=1; consumes real tokens)",
    )


# A canary file that existed in every pre-port commit; if it's in a commit's
# tree, the rest of the old bash impl is there too.
CANARY = "scripts/on-pre-edit.sh"


def _find_last_commit_with_old_bash() -> str | None:
    """Walk history newest→oldest, return the first sha whose tree has CANARY."""
    try:
        # All reachable commits. Capped at 200 to keep CI fast; in practice the
        # baseline is one commit back.
        log = subprocess.run(
            ["git", "-C", str(REPO), "log", "--all", "--format=%H", "-n", "200"],
            capture_output=True,
            text=True,
            check=True, encoding="utf-8", errors="replace")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    for sha in log.stdout.splitlines():
        sha = sha.strip()
        if not sha:
            continue
        # cat-file -e exits 0 if blob exists at that ref, 128 otherwise.
        r = subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", f"{sha}:{CANARY}"],
            capture_output=True,
            check=False, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return sha
    return None


@pytest.fixture(scope="session")
def old_plugin_root(tmp_path_factory) -> Path:
    sha = _find_last_commit_with_old_bash()
    if sha is None:
        pytest.skip(
            f"no commit reachable from this clone contains {CANARY}; "
            "parity oracle unavailable (try fetch-depth: 0 in CI)"
        )
    out = tmp_path_factory.mktemp("old-plugin")
    # `git archive` emits a binary tar stream — must NOT decode as text.
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", sha],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(out)],
        input=archive.stdout,
        check=True,
    )
    for p in (out / "bin").iterdir():
        os.chmod(p, 0o755)
    for p in (out / "scripts").glob("*.sh"):
        os.chmod(p, 0o755)
    return out
