#!/usr/bin/env bash
# pyfind.sh — locate a Python 3 interpreter portably and exec the dispatcher.
#
# Sourced by scripts/run-hook and every bin/* launcher. There is no single
# interpreter name that works on all three platforms (macOS has only python3,
# Git for Windows ships python or "py -3", some Linux distros expose python),
# so we probe in order and fall back to a no-op exit if nothing is found —
# matching the existing convention that the plugin is silently inert when its
# prerequisites are missing.
#
# Inputs after sourcing:
#   HARNESS_KIT_ROOT must be set to the plugin root.
#   HARNESS_DISPATCH must be set to the dispatcher name (e.g. "pre-edit").
# Any further "$@" args are forwarded to the dispatcher.

set -uo pipefail

if [ -z "${HARNESS_KIT_ROOT:-}" ]; then
  echo "harness-kit: HARNESS_KIT_ROOT not set" >&2
  exit 0
fi
if [ -z "${HARNESS_DISPATCH:-}" ]; then
  echo "harness-kit: HARNESS_DISPATCH not set" >&2
  exit 0
fi

export HARNESS_KIT_ROOT

_pyfind_pick() {
  if [ -n "${HARNESS_PY:-}" ] && command -v "${HARNESS_PY%% *}" >/dev/null 2>&1; then
    printf '%s' "$HARNESS_PY"
    return 0
  fi
  for c in python3 python "py -3"; do
    head=${c%% *}
    if command -v "$head" >/dev/null 2>&1; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}

_HARNESS_PY="$(_pyfind_pick)" || {
  # Silent no-op so an un-prepared environment doesn't disrupt the user.
  # Print to stderr so a debugger can see what happened.
  echo "harness-kit: Python 3 not found on PATH (need 'python3', 'python', or 'py -3')" >&2
  exit 0
}

_HARNESS_MAIN="$HARNESS_KIT_ROOT/scripts/harness_main.py"
if [ ! -f "$_HARNESS_MAIN" ]; then
  echo "harness-kit: dispatcher missing at $_HARNESS_MAIN" >&2
  exit 0
fi

# Word-split _HARNESS_PY so 'py -3' becomes two argv entries.
# shellcheck disable=SC2086
exec $_HARNESS_PY "$_HARNESS_MAIN" "$HARNESS_DISPATCH" "$@"
