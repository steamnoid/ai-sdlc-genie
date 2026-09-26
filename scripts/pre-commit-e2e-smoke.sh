#!/usr/bin/env bash
# The cheap real-agent gate: one repository, one provider, no retry storm.
#
# Opt-in on purpose. A commit hook that silently calls a paid endpoint is a
# surprise bill, so the hook is installed but inert until explicitly enabled:
#
#     AISDLC_E2E_SMOKE=1 git commit
#
# or permanently, in your shell profile:
#
#     export AISDLC_E2E_SMOKE=1
#
# To run the full real-agent matrix by hand, see AGENTS.md §6.
set -euo pipefail

if [[ "${AISDLC_E2E_SMOKE:-0}" != "1" ]]; then
  exit 0
fi

# §4 forbids hard-coding a repository; the test falls back to a small public
# default when this is unset.
repo="${E2E_REPOSITORY:-pallets/click}"

# The model is resolved by aisdlc.llm.factory, which calls load_dotenv() at
# import. A shell that has not exported LLM_MODEL therefore cannot report it,
# so say so rather than print an empty value that looks like a misconfiguration.
if [[ -n "${LLM_MODEL:-}" ]]; then
  model="$LLM_MODEL"
elif [[ -f .env ]] && grep -q '^LLM_MODEL=' .env; then
  model="from .env"
else
  model="unset"
fi

printf 'ai-sdlc: e2e_smoke against %s (provider=%s model=%s)\n' \
  "$repo" "${LLM_PROVIDER:-openai}" "$model"

uv run pytest -m e2e_smoke -q
