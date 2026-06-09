"""Hook handlers — one module per Claude Code hook event.

Each module exposes `run() -> int` that the dispatcher invokes; the return
value becomes the process exit code.
"""
