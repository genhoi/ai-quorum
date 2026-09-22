#!/usr/bin/env bash
# shellcheck disable=SC2034  # variables here are used by the scripts that source this file
# The single place for defaults: who advises, who judges, models, effort, language.
# Precedence: environment variable → current Codex parent turn (CODEX_MODEL/EFFORT only) →
# ~/.config/quorum/config.env → values below. Inspect/change: `quorum config [set KEY VALUE]`.

if [ -n "${CODEX_THREAD_ID:-}" ] && { [ -z "${CODEX_MODEL:-}" ] || [ -z "${CODEX_EFFORT:-}" ]; }; then
  if qr_codex_context="$(python3 "$(dirname "${BASH_SOURCE[0]}")/codex_context.py" 2>&1)"; then
    CODEX_MODEL="${qr_codex_context%%$'\n'*}"
    CODEX_EFFORT="${qr_codex_context#*$'\n'}"
  else
    export QR_CODEX_PARENT_ERROR="$qr_codex_context"
  fi
  unset qr_codex_context
fi

QR_CONFIG_FILE="${QUORUM_CONFIG:-$HOME/.config/quorum/config.env}"
if [ -f "$QR_CONFIG_FILE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"; line="${line#"${line%%[![:space:]]*}"}"
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]] || continue
    k="${BASH_REMATCH[1]}"; v="${BASH_REMATCH[2]}"; v="${v%"${v##*[![:space:]]}"}"
    v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
    [ -n "${!k:-}" ] || export "$k=$v"
  done < "$QR_CONFIG_FILE"
fi

# --- roles ---
: "${QUORUM_ADVISORS:=codex,grok,glm}"   # three families by default; the judge must be a fourth one or a different family from the winner
: "${QUORUM_JUDGE:=fable}"
: "${QUORUM_ADVISOR_EFFORT:=max}"        # claude family only (glm, kimi, opus, fable as an advisor)
: "${QUORUM_JUDGE_EFFORT:=high}"         # the judge reads three short answers; high is enough and cheaper
: "${QUORUM_RETRY:=1}"                   # judge rounds after "no acceptable answer": 0 or 1
# --- language of prompts and answers: ru (en not shipped yet) ---
: "${QUORUM_LANG:=ru}"
# --- how ignored dependencies get into the snapshot: copy | hardlink | symlink | none ---
: "${QUORUM_DEPS:=copy}"
# --- limits (seconds) ---
: "${QUORUM_TIMEOUT:=3600}"              # per advisor / refuter
: "${QUORUM_JUDGE_TIMEOUT:=1500}"
# --- models ---
: "${GLM_MODEL:=glm-5.3[1m]}";      : "${GLM_SMALL_MODEL:=glm-5.3-flash}"
: "${KIMI_MODEL:=kimi-for-coding[1m]}";   : "${KIMI_CLI_MODEL:=kimi-code/kimi-for-coding}"
: "${OPUS_MODEL:=opus}"
: "${FABLE_MODEL:=fable}"
: "${GROK_MODEL:=grok-4.7}"
: "${CODEX_MODEL:=gpt-6-astra}"
: "${GROK_EFFORT:=xhigh}";          : "${CODEX_EFFORT:=xhigh}"
# --- endpoints ---
: "${ZAI_BASE_URL:=https://api.z.ai/api/anthropic}"
: "${KIMI_BASE_URL:=https://api.kimi.com/coding/}"
export QUORUM_ADVISORS QUORUM_JUDGE QUORUM_ADVISOR_EFFORT QUORUM_JUDGE_EFFORT QUORUM_RETRY QUORUM_LANG QUORUM_DEPS \
  QUORUM_TIMEOUT QUORUM_JUDGE_TIMEOUT GLM_MODEL GLM_SMALL_MODEL KIMI_MODEL KIMI_CLI_MODEL OPUS_MODEL FABLE_MODEL \
  GROK_MODEL CODEX_MODEL GROK_EFFORT CODEX_EFFORT ZAI_BASE_URL KIMI_BASE_URL

QR_CONFIG_KEYS="QUORUM_ADVISORS QUORUM_JUDGE QUORUM_ADVISOR_EFFORT QUORUM_JUDGE_EFFORT QUORUM_RETRY QUORUM_LANG QUORUM_DEPS QUORUM_TIMEOUT QUORUM_JUDGE_TIMEOUT GLM_MODEL GLM_SMALL_MODEL KIMI_MODEL KIMI_CLI_MODEL OPUS_MODEL FABLE_MODEL GROK_MODEL CODEX_MODEL GROK_EFFORT CODEX_EFFORT ZAI_BASE_URL KIMI_BASE_URL"
