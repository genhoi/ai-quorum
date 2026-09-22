#!/usr/bin/env bash
# Stub backend for CI and dry runs: answers according to the role in the prompt, no network.
# Never selected automatically (check fails unless QUORUM_FAKE=1). Variants fake:a, fake:b, fake:c
# count as different families, so a run can be exercised with the stub alone.
# The answer texts live in tests/samples/fake-*.md; the role is read from $QR_DIR/role.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
emit() { # emit FILE — wrap a markdown answer into a minimal claude stream-json log
  python3 - "$1" "$(cat "$QR_DIR/session" 2>/dev/null || echo fake-session)" <<'PY'
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({"type": "system", "subtype": "init", "session_id": sys.argv[2], "model": "stub"}))
print(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "stub", "content": [
    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "git log -1"}}]}}))
print(json.dumps({"type": "result", "subtype": "success", "session_id": sys.argv[2], "num_turns": 2,
                  "total_cost_usd": 0.0, "duration_ms": 1200, "result": text,
                  "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0}}, ensure_ascii=False))
PY
}
case "$1" in
  run|ask)
    role="$(cat "$QR_DIR/role" 2>/dev/null || echo advisor)"
    stage="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("stage","plan"))' "$QR_RUN/meta.json" 2>/dev/null || echo plan)"
    backend="$(cat "$QR_DIR/backend" 2>/dev/null || echo fake)"
    variant="${QR_FAKE_VARIANT:-${backend#*:}}"; [ "$variant" != "$backend" ] || variant=a
    s="$QR_SKILL_DIR/tests/samples"
    for f in "$s/fake-$role-$stage-$variant.md" "$s/fake-$role-$stage.md" "$s/fake-$role-$variant.md" "$s/fake-$role.md"; do [ -f "$f" ] && break; done
    [ -f "$f" ] || die "fake: no sample for role $role"
    [ ! -d "$QR_SNAPSHOT" ] || cp "$f" "$QR_SNAPSHOT/ANSWER.md" 2>/dev/null || true
    sleep "${FAKE_DELAY:-1}"
    emit "$f" ;;
  format) echo claude-stream-json ;;
  check)  [ -n "${QUORUM_FAKE:-}" ] || { echo "stub backend (set QUORUM_FAKE=1 or name it explicitly)"; exit 1; }; echo "ok — stub" ;;
  *) die "fake backend: unknown command $1" ;;
esac
exit 0
