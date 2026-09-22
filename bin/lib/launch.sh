#!/usr/bin/env bash
# Background wrapper for one job (advisor, judge, retry, refuter): status files, timeout, extraction.
# Usage: launch.sh RUN JOB   — the job directory holds: backend, role, mode (run|ask), prompt.md,
# snapshot (directory or symlink), session. QR_EFFORT is inherited from the caller.
# The whole body lives in main() so bash parses the file completely before running it:
# editing this file while a job is in flight must not break the wrapper.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/finalize.sh"

main() {
  local RUN="$1" J="$2" D="$1/$2"
  local backend mode; backend="$(cat "$D/backend")"; mode="$(cat "$D/mode" 2>/dev/null || echo run)"
  export QR_RUN="$RUN" QR_JOB="$J" QR_DIR="$D" QR_SNAPSHOT="$D/snapshot" QR_PROMPT="$D/prompt.md"
  export QR_PROJ_ROOT="$(cat "$RUN/project_root")" QR_TIMEOUT="$(cat "$D/timeout" 2>/dev/null || cat "$RUN/timeout")"
  local BACKEND="$QR_SKILL_DIR/bin/backends/${backend%%:*}.sh"
  [ -f "$BACKEND" ] || { echo "failed:no-backend" > "$D/status"; return 1; }
  echo running > "$D/status"; now_iso > "$D/started"
  if [ "$mode" = ask ]; then
    timeout -k 60 "$QR_TIMEOUT" bash "$BACKEND" ask "$(cat "$D/prompt.md")" > "$D/raw" 2> "$D/stderr.log"
  else
    timeout -k 60 "$QR_TIMEOUT" bash "$BACKEND" run > "$D/raw" 2> "$D/stderr.log"
  fi
  local code=$?
  finalize_job "$RUN" "$J" "$code"
  # the run drives itself: the last job to finish launches the next role (judge, retry, refuter)
  # or writes the verdict. `quorum wait` does the same, so nothing depends on the implementer polling.
  bash "$QR_SKILL_DIR/bin/quorum" advance "$RUN" >> "$RUN/advance.log" 2>&1 || true
}
main "$@"
exit $?
