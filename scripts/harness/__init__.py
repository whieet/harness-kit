"""harness-kit — Python core.

All real logic lives in this package. The bash launchers in scripts/run-hook and
bin/* exist only to locate a Python 3 interpreter and exec the dispatcher in
harness_main.py — keeping the codebase single-source across macOS, Linux, and
Windows (with Git Bash).
"""
__all__ = ["context", "cli", "util", "gitutil"]
