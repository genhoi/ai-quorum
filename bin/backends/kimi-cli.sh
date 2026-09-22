#!/usr/bin/env bash
# Kimi via the native kimi-code CLI (OAuth). Fallback path: the OAuth token expires every few days.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
KIMI_BIN="${KIMI_BIN:-$HOME/.kimi-code/bin/kimi}"; command -v kimi >/dev/null && KIMI_BIN="${KIMI_BIN:-kimi}"
case "$1" in
  run)
    cd "$QR_SNAPSHOT" || exit 1
    exec "$KIMI_BIN" -p "$(cat "$QR_PROMPT")" --output-format stream-json -m "$KIMI_CLI_MODEL" ;;
  ask)
    src="$(cat "$QR_DIR/parent" 2>/dev/null || echo "$QR_DIR")"
    sid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id") or "")' "$src/meta.json")"
    [ -n "$sid" ] || die "kimi-cli: session id not found in $src/meta.json"
    cd "$QR_SNAPSHOT" || exit 1
    exec "$KIMI_BIN" -S "$sid" -p "$2" --output-format stream-json ;;
  format) echo kimi-stream-json ;;
  check)
    [ -x "$KIMI_BIN" ] || { echo "kimi binary not found (~/.kimi-code/bin/kimi)"; exit 1; }
    [ -n "$(ls -A "$HOME/.kimi-code/credentials" 2>/dev/null)" ] || { echo "no kimi OAuth credentials (kimi login)"; exit 1; }
    echo "ok — $KIMI_CLI_MODEL (OAuth)" ;;
  *) die "kimi-cli backend: unknown command $1" ;;
esac
exit 0
