#!/usr/bin/env bash
# config.sh — sourced by every harness-kit hook + bin script.
#
# Responsibilities:
#   1. Resolve the PROJECT root robustly (plugin scripts run from the plugin
#      cache via ${CLAUDE_PLUGIN_ROOT}, so BASH_SOURCE cannot locate the project).
#   2. Locate the project-tracked config at <project>/.harness/config.json.
#   3. Provide python3-based JSON accessors (python3 is already a harness
#      dependency everywhere; jq is intentionally NOT required).
#
# All snippets passed to harness_py MUST be single-quoted by the caller so the
# shell does not expand $ / backticks inside the python source.

# --- resolve project root (4-level fallback) -------------------------------
# 1. HARNESS_PROJECT_DIR  (a hook script may set this from stdin 'cwd')
# 2. CLAUDE_PROJECT_DIR   (env injected by Claude Code)
# 3. git rev-parse --show-toplevel (from current cwd)
# 4. walk up from PWD looking for .harness/ or .git/
harness_resolve_project_dir() {
  local d
  if [ -n "${HARNESS_PROJECT_DIR:-}" ]; then printf '%s\n' "$HARNESS_PROJECT_DIR"; return 0; fi
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then printf '%s\n' "$CLAUDE_PROJECT_DIR"; return 0; fi
  if d=$(git rev-parse --show-toplevel 2>/dev/null); then printf '%s\n' "$d"; return 0; fi
  d="$PWD"
  while [ "$d" != "/" ] && [ -n "$d" ]; do
    if [ -d "$d/.harness" ] || [ -d "$d/.git" ]; then printf '%s\n' "$d"; return 0; fi
    d=$(dirname "$d")
  done
  printf '%s\n' "$PWD"
}

harness_set_paths() {
  HARNESS_PROJECT_DIR="$(harness_resolve_project_dir)"
  HARNESS_CONFIG="${HARNESS_PROJECT_DIR}/.harness/config.json"
  export HARNESS_PROJECT_DIR HARNESS_CONFIG
}
harness_set_paths

# harness_init_from_stdin <event-json> — if the hook payload carries a 'cwd',
# adopt it as the authoritative project dir, then re-resolve config path.
harness_init_from_stdin() {
  local json="${1:-}"
  [ -z "$json" ] && return 0
  local cwd
  cwd=$(printf '%s' "$json" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("cwd", "") or "")
except Exception:
    print("")
' 2>/dev/null || true)
  if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    # prefer the git toplevel that contains cwd, else cwd itself
    local top
    top=$( (cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null) || true)
    HARNESS_PROJECT_DIR="${top:-$cwd}"
    HARNESS_CONFIG="${HARNESS_PROJECT_DIR}/.harness/config.json"
    export HARNESS_PROJECT_DIR HARNESS_CONFIG
  fi
  return 0
}

harness_has_config() { [ -f "$HARNESS_CONFIG" ]; }

# harness_state_dir — per-project, gitignored scratch dir for loop counters and
# the trace log. Project-local (not global plugin data) so two projects never
# share counters; init writes `.harness/.gitignore` to keep state/ out of git.
harness_state_dir() {
  local d="${HARNESS_PROJECT_DIR}/.harness/state"
  mkdir -p "$d" 2>/dev/null || true
  printf '%s\n' "$d"
}

# harness_cap_enabled <name> — is config.enabledCapabilities.<name> on?
# Returns 0 (enabled) / 1 (disabled). When the key is ABSENT: defaults ON for
# stable capabilities (back-compat — they always ran), OFF for experimental ones.
# Engines guard with:  harness_cap_enabled loopDetection || exit 0
harness_cap_enabled() {
  HK_CAP="$1" harness_py '
import os, sys
caps = cfg.get("enabledCapabilities", {})
name = os.environ["HK_CAP"]
experimental_off = {"evaluatorAutoDispatch"}
default = (name not in experimental_off)
sys.exit(0 if caps.get(name, default) else 1)
'
}

# harness_py <python-snippet> — exec the snippet with these names in scope:
#   cfg  : dict parsed from .harness/config.json ({} if absent/invalid)
#   proj : project root (str)
#   json, os, sys
# The snippet is argv[3]; the heredoc below is a fixed loader. This keeps all
# JSON logic in python and isolates the snippet from shell quoting.
harness_py() {
  python3 - "$HARNESS_PROJECT_DIR" "$HARNESS_CONFIG" "$1" <<'PYLOADER'
import json, os, sys
proj, cfgp, snippet = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = {}
if os.path.exists(cfgp):
    try:
        with open(cfgp) as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
exec(snippet)
PYLOADER
}

# harness_cfg_get <dotted.path> [default] — print one scalar value from config.
# Nested dict keys only (arrays handled by per-script python snippets).
harness_cfg_get() {
  HKEY="$1" HDEF="${2:-}" harness_py '
import os
path = os.environ["HKEY"].split(".")
v = cfg
for p in path:
    if isinstance(v, dict) and p in v:
        v = v[p]
    else:
        v = None
        break
if v is None:
    print(os.environ.get("HDEF",""))
elif isinstance(v, str):
    print(v)
else:
    print(json.dumps(v))
'
}
