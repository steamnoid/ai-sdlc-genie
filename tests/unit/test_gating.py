"""Behaviour the real-dependency tiers need from the gate helpers.

Rule 0.8 requires a real-agent tier to skip *loudly* when configuration is
missing, and forbids a green run that never reached a model. The decision
therefore lives in an importable module rather than inside conftest.py, so
it can be tested with no network, no credentials and no fixtures.

These tests import the module lazily so that a missing implementation
surfaces as a skipped test with a printed reason — the same shape the real
tiers are required to use — rather than a collection error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The gate helpers are test infrastructure, not an installed package, so the
# repository's tests/ directory goes on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _gating() -> object:
    """Import the gate module, or skip with the reason printed.

    Returns:
        The imported module, or skips the calling test.
    """
    return pytest.importorskip(
        "support.gating",
        reason="support.gating is not implemented yet",
    )


class TestRequireLLMCredential:
    def test_missing_credential_reports_the_variable_to_set(self) -> None:
        """The reason names the variable, not merely that something is absent."""
        gating = _gating()

        with pytest.raises(gating.MissingCredential) as excinfo:
            gating.require_llm_credential(provider="openai", environ={})

        assert "OPENAI_API_KEY" in excinfo.value.reason
        assert "openai" in excinfo.value.reason

    def test_ollama_needs_no_credential(self) -> None:
        """A local provider must run without secrets, so §29 stays reachable."""
        gating = _gating()

        assert gating.require_llm_credential(provider="ollama", environ={}) is None

    def test_llm_api_key_is_accepted_as_an_alias(self) -> None:
        """Both accepted variables satisfy the provider."""
        gating = _gating()

        source_variable = gating.require_llm_credential(
            provider="openai", environ={"LLM_API_KEY": "placeholder-for-local-server"}
        )

        assert source_variable == "LLM_API_KEY"

    def test_credential_value_is_never_echoed(self) -> None:
        """A skip reason must not carry the secret it is complaining about."""
        gating = _gating()
        secret = "ghp_this_must_never_be_printed_in_a_skip_reason"

        result = gating.require_llm_credential(
            provider="openai", environ={"OPENAI_API_KEY": secret}
        )

        assert result is not None
        assert secret not in result


class TestRequireE2ERepository:
    def test_unset_repository_falls_back_to_a_known_public_default(self) -> None:
        """A run must be possible with no configuration at all."""
        gating = _gating()

        assert gating.require_e2e_repository(environ={}) == "pallets/click"

    def test_malformed_repository_is_refused_with_an_actionable_reason(self) -> None:
        """A bad override fails loudly rather than being coerced."""
        gating = _gating()

        with pytest.raises(gating.MissingCredential) as excinfo:
            gating.require_e2e_repository(environ={"E2E_REPOSITORY": "not-a-valid-id"})

        reason = excinfo.value.reason
        assert "E2E_REPOSITORY" in reason
        assert "owner/name" in reason

    def test_configured_repository_is_returned_verbatim(self) -> None:
        """An explicit owner/name pair wins, since §4 forbids hard-coding one."""
        gating = _gating()

        resolved = gating.require_e2e_repository(environ={"E2E_REPOSITORY": "pallets/flask"})

        assert resolved == "pallets/flask"


class TestDescribeProvider:
    def test_describes_the_configured_provider_and_model(self) -> None:
        """A real run must always state which model produced its output."""
        gating = _gating()

        label = gating.describe_provider(environ={"LLM_PROVIDER": "ollama", "LLM_MODEL": "qwen3"})

        assert "ollama" in label
        assert "qwen3" in label

    def test_binds_the_precedence_of_a_partial_override(self) -> None:
        """With one variable set, the other is named explicitly, not blank."""
        gating = _gating()

        label = gating.describe_provider(environ={"LLM_PROVIDER": "ollama"})

        assert "provider=ollama" in label
        assert "model=<unset>" in label

    def test_unset_provider_falls_back_to_the_factory_default(self) -> None:
        """No LLM_PROVIDER still yields a concrete label."""
        gating = _gating()

        label = gating.describe_provider(environ={"LLM_MODEL": "gpt-5"})

        assert "openai" in label
        assert "gpt-5" in label
