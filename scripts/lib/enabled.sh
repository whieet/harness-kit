#!/usr/bin/env bash
# enabled.sh — sourced FIRST by every hook entry script.
#
# Contract for the sourcing hook script:
#   INPUT="$(cat 2>/dev/null || true)"          # read the event JSON once
#   source "<scriptdir>/lib/enabled.sh"          # sets up config, may exit 0
#   # ... if we get here, the project IS harness-initialized ...
#
# Behavior:
#   - sources config.sh (path resolution + JSON accessors)
#   - adopts the project cwd from the hook payload ($INPUT) if present
#   - NO-OPS (exit 0) when the project has no .harness/config.json, i.e. the
#     plugin is installed but `/harness-kit:init` was never run. This makes the
#     plugin completely inert on un-initialized repos.

_HARNESS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./config.sh
source "${_HARNESS_LIB_DIR}/config.sh"

harness_init_from_stdin "${INPUT:-}"

if ! harness_has_config; then
  exit 0
fi
