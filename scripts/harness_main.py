#!/usr/bin/env python3
"""harness_main.py — single Python entry exec'd by every bash launcher.

The launcher passes the dispatcher name as argv[1] (e.g. "pre-edit" or
"harness-verify") plus any extra args, and forwards stdin untouched.
"""
from __future__ import annotations

import os
import sys


def _ensure_package_on_path() -> None:
    """Allow `import harness` regardless of where Python was invoked from."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def _ensure_kit_root() -> None:
    """Export HARNESS_KIT_ROOT so handlers can find templates/, bin/, etc.

    Honors a pre-existing value (set by the bash launcher); falls back to the
    parent of this script's directory.
    """
    if os.environ.get("HARNESS_KIT_ROOT"):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    os.environ["HARNESS_KIT_ROOT"] = os.path.abspath(os.path.join(here, ".."))


if __name__ == "__main__":
    _ensure_package_on_path()
    _ensure_kit_root()

    from harness.cli import main

    sys.exit(main(sys.argv[1:]))
