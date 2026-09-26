"""Shared fixtures and the opt-in boundary for the real-dependency tiers.

Rule 0.6 keeps the default run free of network and credentials; Rule 0.8
requires a real tier to skip with a printed reason rather than pass
vacuously. The decisions live in :mod:`tests.support.gating` so they can be
unit tested, and this module only wires them into pytest.

Nothing here imports a model or a client. A fixture that needs credentials
skips before doing any work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# tests/ is not an installed package, so the shared helpers are imported by
# path. This keeps the import identical from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support.gating import MissingCredential, ProviderConfig


def _provider_config() -> ProviderConfig:
    """Resolve the real-dependency configuration or skip with the reason.

    Returns:
        The resolved provider configuration.

    Raises:
        pytest.skip.Exception: Always, when configuration is unusable. The
            printed reason names the variable to set, so the skip is
            actionable rather than mysterious.
    """
    try:
        return ProviderConfig.from_env(os.environ)
    except MissingCredential as error:
        pytest.skip(f"real-dependency tier skipped: {error.reason}")


@pytest.fixture(scope="session")
def provider_config() -> ProviderConfig:
    """The provider, repository and label the real tiers will run against.

    Session scoped because resolving it is cheap and the answer must be
    identical for every test in a run, otherwise one test could silently
    use a different model from another.
    """
    return _provider_config()


@pytest.fixture(scope="session")
def e2e_repository_id(provider_config: ProviderConfig) -> str:
    """The ``owner/name`` repository the real-agent tiers analyse (§4).

    Configurable through ``E2E_REPOSITORY`` so no repository is hard-coded.
    """
    return provider_config.repository_id


@pytest_asyncio.fixture
async def real_llm(provider_config: ProviderConfig):
    """A real LangChain chat model, closed when the test finishes.

    A fresh instance per test keeps the provider's async client inside the
    event loop that created it. The close runs in that same loop, which is
    the whole point: closing on a different loop leaves the transport bound
    to a loop that has already finished.

    Yields:
        A chat model ready for ``ainvoke``.

    Raises:
        pytest.skip.Exception: If the provider cannot be constructed. An
            unreachable local model is a skip, not a silent pass, because a
            green run that never called a model is a lie.
    """
    from aisdlc.llm.factory import LLMConfigurationError, LLMFactory

    try:
        model = LLMFactory.create_model()
    except LLMConfigurationError as error:
        pytest.skip(f"real-dependency tier skipped: provider unusable ({error})")

    print(f"\nreal-agent tier running against {provider_config.description}")

    try:
        yield model
    finally:
        client = getattr(model, "async_client", None)
        close = getattr(client, "aclose", None)
        if callable(close):
            await close()
