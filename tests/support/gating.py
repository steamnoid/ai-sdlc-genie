"""Walking skeleton for the gate helpers. Behaviour is intentionally absent.

This file exists only so the tests in tests/unit/test_gating.py can fail on
assertions rather than on a missing import. Every function here is wrong on
purpose and is replaced by the real implementation in the next commit.
"""

from __future__ import annotations

from collections.abc import Mapping


class MissingCredential(RuntimeError):
    """Placeholder. Carries no reason yet."""

    reason = ""


def require_llm_credential(*, provider: str, environ: Mapping[str, str]) -> str | None:
    """Placeholder: never raises, so the credential tests fail."""
    return None


def require_e2e_repository(*, environ: Mapping[str, str]) -> str:
    """Placeholder: returns nothing, so the repository tests fail."""
    return ""


def describe_provider(*, environ: Mapping[str, str]) -> str:
    """Placeholder: names neither provider nor model, so the label tests fail."""
    return ""
