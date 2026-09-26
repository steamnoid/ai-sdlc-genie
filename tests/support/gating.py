"""Why the real-dependency tiers skip, decided without pytest.

Rule 0.8 requires that a missing key or an unreachable provider produces a
skip **with the reason printed**, and forbids a green run that never reached
a model. The decision therefore lives here, in a plain module with no pytest
import, so it can be unit tested with no network, no credentials and no
fixtures. conftest.py only translates these outcomes into ``pytest.skip``.

Every reason names the variable or command that would make the test
runnable, and no reason ever contains a credential value (§27).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Provider assumed when LLM_PROVIDER is unset. Mirrors LLMConfig.from_env.
DEFAULT_PROVIDER = "openai"

#: Credential variables accepted for the openai provider, in precedence order.
OPENAI_CREDENTIAL_VARS = ("OPENAI_API_KEY", "LLM_API_KEY")

#: A small, stable public repository used when E2E_REPOSITORY is unset.
#: Overridable precisely because §4 forbids hard-coding a repository.
DEFAULT_E2E_REPOSITORY = "pallets/click"


class MissingCredential(RuntimeError):
    """Raised when a real-dependency test cannot run for want of configuration.

    Attributes:
        reason: A message naming what to set, safe to print.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def require_llm_credential(*, provider: str, environ: Mapping[str, str]) -> str | None:
    """Assert that the provider has whatever credential it needs.

    Args:
        provider: Either ``openai`` (covering OpenAI-compatible servers) or
            ``ollama``.
        environ: Environment mapping to read. Injected so tests never touch
            the real environment.

    Returns:
        The name of the variable that supplied the credential, or ``None``
        when the provider needs none.

    Raises:
        MissingCredential: If the openai provider has no credential.
    """
    if provider != "openai":
        return None

    for variable in OPENAI_CREDENTIAL_VARS:
        if environ.get(variable):
            return variable

    names = " or ".join(OPENAI_CREDENTIAL_VARS)
    raise MissingCredential(
        f"provider 'openai' needs a credential: set {names}. A local "
        "OpenAI-compatible server may use a placeholder value, or run with "
        "LLM_PROVIDER=ollama to use a local model instead."
    )


def require_e2e_repository(*, environ: Mapping[str, str]) -> str:
    """Resolve which public repository the real-agent tests should analyse.

    §4 forbids hard-coding a single repository, so the identifier is
    configurable and the default is only a fallback.

    Args:
        environ: Environment mapping to read.

    Returns:
        A repository identifier in ``owner/name`` form.

    Raises:
        MissingCredential: If ``E2E_REPOSITORY`` is set to something unusable.
    """
    configured = (environ.get("E2E_REPOSITORY") or "").strip()
    if not configured:
        return DEFAULT_E2E_REPOSITORY

    parts = configured.split("/")
    if len(parts) != 2 or not all(parts):
        raise MissingCredential(
            f"E2E_REPOSITORY={configured!r} is not usable; expected 'owner/name', "
            f"for example {DEFAULT_E2E_REPOSITORY!r}."
        )
    return configured


def describe_provider(*, environ: Mapping[str, str]) -> str:
    """Build a human-readable label for the provider under test.

    The label is printed by the real tiers so a run always states which model
    produced its output. §29 makes the provider part of the architecture, so
    it must never be anonymous.

    Args:
        environ: Environment mapping to read.

    Returns:
        A label naming the provider and model, for example
        ``provider=ollama model=qwen3``. A missing model is reported as
        ``<unset>`` rather than as an empty string, so a blank in the output
        is never ambiguous.
    """
    provider = (environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    model = (environ.get("LLM_MODEL") or "").strip() or "<unset>"
    return f"provider={provider} model={model}"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """The environment a real-dependency test will actually run against.

    Attributes:
        provider: Provider name passed through to the model factory.
        repository_id: Repository the agent should analyse.
        description: Label for run output.
    """

    provider: str
    repository_id: str
    description: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> ProviderConfig:
        """Build the configuration, refusing to proceed if it is unusable.

        Args:
            environ: Environment mapping to read.

        Returns:
            The resolved configuration.

        Raises:
            MissingCredential: If a required variable is absent or malformed.
        """
        provider = (environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
        require_llm_credential(provider=provider, environ=environ)
        return cls(
            provider=provider,
            repository_id=require_e2e_repository(environ=environ),
            description=describe_provider(environ=environ),
        )
