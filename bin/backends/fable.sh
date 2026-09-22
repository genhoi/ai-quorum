#!/usr/bin/env bash
# Claude Fable via the user's own subscription (OAuth in ~/.claude). Default judge: reads three
# short answers, so it is cheap in this role even though it is the most expensive model.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/claude_backend.sh"
backend_env() {
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_FABLE_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
  export CLAUDE_EXTRA_ARGS="--model $FABLE_MODEL --setting-sources project,local"
}
backend_check() {
  [ -f "$HOME/.claude/.credentials.json" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "not logged in to Claude (claude auth login) and no ANTHROPIC_API_KEY"; exit 1; }
  echo "ok — $FABLE_MODEL via Claude subscription"
}
claude_dispatch "$@"
exit $?
