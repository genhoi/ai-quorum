#!/usr/bin/env bash
# Finalize one job directory: extract the answer, write meta.json and the status.
# Shared by launch.sh (normal completion) and bin/quorum (a wrapper that died without a status).
# Usage: finalize_job RUN JOB EXIT_CODE   (EXIT_CODE may be "died")

nonblank() { [ -n "$(tr -d '[:space:]' < "$1" 2>/dev/null)" ]; }

partial_reason() { # partial_reason DIR EXIT_CODE
  local d="$1" code="$2" reason="" err=""
  case "$code" in
    0|"")        ;;
    124|137|143) reason="timeout or kill";;
    died)        reason="killed";;
    *)           reason="exit $code";;
  esac
  if [ -n "$reason" ] && [ -f "$d/meta.json" ]; then
    err="$(py error "$d/meta.json" 2>/dev/null)"
    [ -z "$err" ] || reason="$reason; $err"
  fi
  printf '%s' "$reason"
}

finalize_job() {
  local code="$3" d="$1/$2"
  local fmt; fmt="$(cat "$d/format" 2>/dev/null || echo text)"
  [ -f "$d/finished" ] || now_iso > "$d/finished"
  py report "$fmt" "$d/raw" > "$d/report.md" 2>> "$d/stderr.log" || true
  py meta   "$fmt" "$d/raw" > "$d/meta.json" 2>> "$d/stderr.log" || true
  # every role is told to duplicate the answer into ANSWER.md in the snapshot — fallback when stream extraction fails
  if ! nonblank "$d/report.md" && nonblank "$d/snapshot/ANSWER.md"; then cp "$d/snapshot/ANSWER.md" "$d/report.md"; fi
  echo "$code" > "$d/exit"
  partial_reason "$d" "$code" > "$d/partial"
  nonblank "$d/partial" || rm -f "$d/partial"
  if nonblank "$d/report.md"; then echo "done" > "$d/status"
  elif [ "$code" = 124 ] || [ "$code" = 137 ]; then echo timeout > "$d/status"
  elif [ "$code" = died ]; then echo died > "$d/status"
  else echo "failed:$code" > "$d/status"; fi
}
