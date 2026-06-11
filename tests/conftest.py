"""tests/conftest.py — pytest setup.

Adds the repo root to sys.path so tests can `from tests._helpers import ...`,
and registers the `live` marker.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))  # so `from harness import ...` works in-process

# Keep interpreter deprecation warnings out of subprocess stderr that tests
# assert on (some Python versions print to stderr on import/runtime). Inherited
# by every subprocess the tests spawn; does not touch this process's own
# (already initialized) warning filters.
os.environ.setdefault("PYTHONWARNINGS", "ignore")


def pytest_configure(config):
    # No pytest.ini/pyproject in this repo — markers are registered here.
    config.addinivalue_line(
        "markers",
        "live: drives a real headless Claude Code instance (needs `claude` CLI + auth; "
        "opt-in via HARNESS_LIVE_E2E=1; consumes real tokens)",
    )
