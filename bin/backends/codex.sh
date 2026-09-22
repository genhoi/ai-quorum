#!/usr/bin/env bash
# OpenAI Codex CLI (ChatGPT subscription), headless `codex exec`, sandbox workspace-write.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
CODEX_BIN="${CODEX_BIN:-codex}"
sandbox_args() {
  if [ -n "${CODEX_NO_SANDBOX:-}" ]; then printf '%s\n' --dangerously-bypass-approvals-and-sandbox
  else printf '%s\n' -s workspace-write -c 'approval_policy="never"' -c 'sandbox_workspace_write.network_access=true'; fi
}
saved_settings() { # model and effort recorded when the job started, so `ask` keeps the same pair
  python3 - "$QR_DIR/codex-settings.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    settings = json.load(stream)
values = [settings[key] for key in ("model", "effort")]
if not all(isinstance(v, str) and v.strip() and "\n" not in v and "\r" not in v for v in values):
    raise ValueError("invalid saved settings")
print(*values, sep="\n")
PY
}
case "$1" in
  run)
    [ -z "${QR_CODEX_PARENT_ERROR:-}" ] || die "$QR_CODEX_PARENT_ERROR"
    python3 - "$QR_DIR/codex-settings.json" "$CODEX_MODEL" "$CODEX_EFFORT" <<'PY' || die "codex: cannot save settings"
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump({"model": sys.argv[2], "effort": sys.argv[3]}, stream)
PY
    mapfile -t sb < <(sandbox_args)
    exec "$CODEX_BIN" exec -C "$QR_SNAPSHOT" "${sb[@]}" \
      -c "model_reasoning_effort=\"$CODEX_EFFORT\"" -m "$CODEX_MODEL" \
      --skip-git-repo-check --json -o "$QR_DIR/last_message.md" - < "$QR_PROMPT" ;;
  ask)
    # the session to continue belongs to the advisor's directory (a retry job points at it via `parent`)
    src="$(cat "$QR_DIR/parent" 2>/dev/null || echo "$QR_DIR")"
    tid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id") or "")' "$src/meta.json")"
    [ -n "$tid" ] || die "codex: thread id not found in $src/meta.json"
    model_args=()
    if [ -f "$src/codex-settings.json" ]; then
      settings="$(QR_DIR="$src" saved_settings)" || die "codex: cannot read saved settings"
      model_args=(-m "${settings%%$'\n'*}" -c "model_reasoning_effort=\"${settings#*$'\n'}\"")
    fi
    mapfile -t sb < <(sandbox_args)
    exec "$CODEX_BIN" exec "${sb[@]}" "${model_args[@]}" resume "$tid" --skip-git-repo-check --json -o "$QR_DIR/last_message.md" "$2" ;;
  format) echo codex-jsonl ;;
  check)
    [ -z "${QR_CODEX_PARENT_ERROR:-}" ] || die "$QR_CODEX_PARENT_ERROR"
    command -v "$CODEX_BIN" >/dev/null || { echo "codex binary not found (see references/setup.md)"; exit 1; }
    "$CODEX_BIN" login status >/dev/null 2>&1 || { echo "codex not logged in: codex login --device-auth"; exit 1; }
    echo "ok — $CODEX_MODEL, effort $CODEX_EFFORT" ;;
  *) die "codex backend: unknown command $1" ;;
esac
exit 0
