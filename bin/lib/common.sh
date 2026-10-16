#!/usr/bin/env bash
# shellcheck disable=SC2034  # variables here are used by the scripts that source this file
# Shared functions for bin/quorum, launch.sh and the backends. Loaded via `source`.

QR_SKILL_DIR="${QR_SKILL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
QR_HOME="${QUORUM_HOME:-$HOME/.local/state/quorum}"
QR_RUNS="$QR_HOME/runs"
QR_CFG="$QR_HOME/cfg"          # isolated CLAUDE_CONFIG_DIR per third-party backend (glm, kimi)
QR_DEFAULT_LINKS="vendor node_modules .venv .env .env.local .env.test"
QR_ALL_BACKENDS="codex grok glm kimi kimi-cli opus fable"

# The orchestrator that called quorum, for the usage journal. Read before defaults.sh: it exports
# CODEX_MODEL, GROK_MODEL and KIMI_MODEL, and after that every caller would look like Codex.
# Environment first, then the first known agent CLI up the process tree.
detect_harness() {
  if [ -n "${QUORUM_ORCHESTRATOR:-}" ]; then printf '%s' "$QUORUM_ORCHESTRATOR"; return; fi
  if [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]; then
    case "${ANTHROPIC_BASE_URL:-}" in
      *z.ai*) printf 'claude-code(glm)';; *kimi*) printf 'claude-code(kimi)';; "") printf 'claude-code';; *) printf 'claude-code(other)';;
    esac; return
  fi
  if env | grep -qE '^ZCODE_'; then printf 'zcode'; return; fi
  if [ -n "${CODEX_THREAD_ID:-}" ] || [ -n "${CODEX_SANDBOX:-}" ]; then printf 'codex'; return; fi
  local pid="$PPID" comm i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    comm="$(ps -o comm= -p "$pid" 2>/dev/null)" || break
    case "$comm" in zcode*) printf 'zcode'; return;; codex*) printf 'codex'; return;; grok*) printf 'grok'; return;; kimi*) printf 'kimi'; return;; esac
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"; [ -n "$pid" ] && [ "$pid" -gt 1 ] || break
  done
  printf 'shell'
}
[ -n "${QR_HARNESS:-}" ] || QR_HARNESS="$(detect_harness)"
export QR_HARNESS

source "$QR_SKILL_DIR/bin/lib/defaults.sh"

die()  { printf 'quorum: %s\n' "$*" >&2; exit 1; }
warn() { printf 'quorum: %s\n' "$*" >&2; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
py() { python3 "$QR_SKILL_DIR/bin/lib/extract.py" "$@"; }

# Both are called inside $(...), where `die` leaves only the subshell: callers check the status.
proj_root() { git rev-parse --show-toplevel 2>/dev/null || die "not a git repository: $PWD (git is required for the snapshot)"; }
proj_name() { local r; r="$(proj_root)" || return 1; basename "$r"; }

# Advisor or judge spec: NAME[:VARIANT][=MODEL][@EFFORT] — grok@xhigh, codex=gpt-6.1-sol@ultra, fake:a.
# Prints "NAME MODEL EFFORT" with "-" for a part that is not given; returns 1 on a malformed spec.
spec_parse() { # spec_parse SPEC
  local s="$1" model="-" effort="-"
  case "$s" in *@*) effort="${s##*@}"; s="${s%@*}";; esac
  case "$s" in *=*) model="${s#*=}"; s="${s%%=*}";; esac
  [[ "$s" =~ ^[a-z][a-z0-9-]*(:[A-Za-z0-9_-]+)?$ ]] && [[ "$effort" =~ ^[a-z-]+$ ]] && [[ "$model" =~ ^[^[:space:]@=]+$ ]] || return 1
  printf '%s %s %s\n' "$s" "$model" "$effort"
}

# Model and effort of one job → the variables its backend reads. Empty = the default stays.
# codex and grok take effort from CODEX_EFFORT / GROK_EFFORT, the claude family from QR_EFFORT,
# kimi-cli has no effort flag.
apply_job_settings() { # apply_job_settings BACKEND MODEL EFFORT
  local m="$2" e="$3"
  case "${1%%:*}" in
    codex)    CODEX_MODEL="${m:-$CODEX_MODEL}"; CODEX_EFFORT="${e:-$CODEX_EFFORT}" ;;
    grok)     GROK_MODEL="${m:-$GROK_MODEL}"; GROK_EFFORT="${e:-$GROK_EFFORT}" ;;
    kimi-cli) KIMI_CLI_MODEL="${m:-$KIMI_CLI_MODEL}" ;;
    glm)      GLM_MODEL="${m:-$GLM_MODEL}" ;;
    kimi)     KIMI_MODEL="${m:-$KIMI_MODEL}" ;;
    opus)     OPUS_MODEL="${m:-$OPUS_MODEL}" ;;
    fable)    FABLE_MODEL="${m:-$FABLE_MODEL}" ;;
  esac
  case "${1%%:*}" in codex|grok|kimi-cli) ;; *) QR_EFFORT="${e:-${QR_EFFORT:-max}}" ;; esac
  export CODEX_MODEL CODEX_EFFORT GROK_MODEL GROK_EFFORT KIMI_CLI_MODEL GLM_MODEL KIMI_MODEL OPUS_MODEL FABLE_MODEL QR_EFFORT
}
effective_settings() { # effective_settings BACKEND — "MODEL EFFORT" the job runs with, after apply_job_settings
  case "${1%%:*}" in
    codex) echo "$CODEX_MODEL $CODEX_EFFORT";; grok) echo "$GROK_MODEL $GROK_EFFORT";; kimi-cli) echo "$KIMI_CLI_MODEL -";;
    glm) echo "$GLM_MODEL $QR_EFFORT";; kimi) echo "$KIMI_MODEL $QR_EFFORT";; opus) echo "$OPUS_MODEL $QR_EFFORT";;
    fable) echo "$FABLE_MODEL $QR_EFFORT";; *) echo "- $QR_EFFORT";;
  esac
}

# Model family of a backend: the judge and the refuter must come from a family other than the
# advisor they check. "name:variant" is allowed (fake:a, fake:b — the same backend twice).
family_of() { # family_of BACKEND
  case "${1%%:*}" in
    codex) echo openai;; grok) echo xai;; glm) echo zhipu;; kimi|kimi-cli) echo moonshot;;
    opus|fable) echo anthropic;; fake) echo "fake-${1#*:}";; *) echo "${1%%:*}";;
  esac
}

# Key from an environment variable or a file (first line).
key_from() { # key_from ENV_NAME FILE
  local v="${!1:-}"
  if [ -n "$v" ]; then printf '%s' "$v"; return 0; fi
  if [ -f "$2" ]; then head -n1 "$2" | tr -d '\r\n'; return 0; fi
  return 1
}

# Latest run of the current project (or an explicit path / name).
resolve_run() { # resolve_run [RUN]
  local r="${1:-}"
  if [ -n "$r" ]; then
    [ -d "$r" ] && { printf '%s' "$(cd "$r" && pwd)"; return; }
    [ -d "$QR_RUNS/$r" ] && { printf '%s' "$QR_RUNS/$r"; return; }
    die "run not found: $r"
  fi
  local p; p="$(proj_name)" || exit 1
  local latest; latest="$(ls -1d "$QR_RUNS/$p"-* 2>/dev/null | sort | tail -n1)"
  [ -n "$latest" ] || die "no runs for project $p (see: quorum runs)"
  printf '%s' "$latest"
}

# Jobs of a run: every subdirectory with a status file. `role` narrows to advisor|judge|retry|refuter.
run_jobs() { # run_jobs RUN [ROLE]
  local run="$1" role="${2:-}" d
  ls -1 "$run" | while read -r d; do
    [ -f "$run/$d/status" ] || continue
    [ -z "$role" ] || [ "$(cat "$run/$d/role" 2>/dev/null)" = "$role" ] || continue
    echo "$d"
  done
}
status_of() { cat "$1/$2/status" 2>/dev/null || echo "unknown"; }
job_busy() { case "$(status_of "$1" "$2")" in queued|running) return 0;; *) return 1;; esac; }

# Snapshot: a temporary commit of the working tree (uncommitted and untracked included,
# .gitignore respected) on top of HEAD. Prints the sha; prints HEAD if the tree is clean.
snapshot_commit() { # snapshot_commit PROJ_ROOT
  local root="$1" idx tree head
  head="$(git -C "$root" rev-parse HEAD)"
  idx="$(mktemp)"; rm -f "$idx"   # git >= 2.43 rejects an existing empty index file
  cp "$root/.git/index" "$idx" 2>/dev/null || true
  GIT_INDEX_FILE="$idx" git -C "$root" add -A >/dev/null 2>&1
  tree="$(GIT_INDEX_FILE="$idx" git -C "$root" write-tree)"
  rm -f "$idx"
  if [ "$tree" = "$(git -C "$root" rev-parse "$head^{tree}")" ]; then
    printf '%s' "$head"
  else
    git -C "$root" commit-tree "$tree" -p "$head" -m "quorum snapshot $(now_iso)"
  fi
}

# Detached worktree at the snapshot commit + ignored dependencies brought in per MODE:
#   copy     — cp -a (default): a real directory, safe to modify, works with docker bind mounts;
#   hardlink — cp -al: instant and free, but an in-place write to a file also changes the original;
#   symlink  — ln -s: instant, but dangling inside a container that mounts the snapshot;
#   none     — nothing.
make_worktree() { # make_worktree PROJ_ROOT COMMIT DEST MODE LINKS...
  local root="$1" commit="$2" dest="$3" mode="$4"; shift 4
  git -C "$root" worktree add --detach --quiet "$dest" "$commit" 2>/dev/null \
    || git -C "$root" worktree add --detach "$dest" "$commit" >/dev/null
  local l
  for l in "$@"; do
    [ -e "$root/$l" ] && [ ! -e "$dest/$l" ] || continue
    mkdir -p "$(dirname "$dest/$l")"
    case "$mode" in
      copy)     cp -a "$root/$l" "$dest/$l" ;;
      hardlink) cp -al "$root/$l" "$dest/$l" 2>/dev/null || cp -a "$root/$l" "$dest/$l" ;;
      symlink)  ln -s "$root/$l" "$dest/$l" ;;
      none)     ;;
      *) die "unknown deps mode: $mode (copy|hardlink|symlink|none)" ;;
    esac
  done
}

deps_report() { # deps_report PROJ_ROOT LINKS...
  local root="$1"; shift
  local l out=""
  for l in "$@"; do [ -e "$root/$l" ] && out="$out $l $(du -sh "$root/$l" 2>/dev/null | cut -f1)"; done
  printf '%s' "${out# }"
}

remove_worktree() { # remove_worktree PROJ_ROOT DEST
  [ -d "$2" ] || return 0
  git -C "$1" worktree remove --force "$2" >/dev/null 2>&1 || rm -rf "$2" 2>/dev/null || true
  git -C "$1" worktree prune >/dev/null 2>&1 || true
}

# Base ref for the acceptance diff: explicit, otherwise the first of main/master/... that exists.
detect_base() { # detect_base PROJ_ROOT [BASE]
  local root="$1" base="${2:-}" c
  if [ -n "$base" ]; then git -C "$root" rev-parse --verify -q "$base^{commit}" >/dev/null || die "base not found: $base"; printf '%s' "$base"; return; fi
  for c in origin/HEAD main master origin/main origin/master develop; do
    if git -C "$root" rev-parse --verify -q "$c^{commit}" >/dev/null; then printf '%s' "$c"; return; fi
  done
  return 1
}

# Deny rules for the claude family: writes only inside the snapshot.
claude_deny_settings() { # claude_deny_settings PROJ_ROOT — single-line JSON (otherwise claude treats the argument as a path)
  python3 - "$1" "$HOME" <<'PYJSON'
import json, sys
root, home = sys.argv[1], sys.argv[2]
deny = ["Bash(git push:*)", "Bash(git push *)"]
for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    deny += [f"{tool}(/{root}/**)", f"{tool}(/{home}/.claude/**)"]
print(json.dumps({"permissions": {"deny": deny}}))
PYJSON
}

uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }
