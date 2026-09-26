"""Model provider factory.

The application never hard-codes a provider: configuration is read once into a
frozen :class:`LLMConfig` and every agent receives a fresh chat model built
from it, so no model instance outlives the event loop that created it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv()

DEFAULT_TEMPERATURE: Final[float] = 0.0
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_MAX_RETRIES: Final[int] = 2
DEFAULT_OLLAMA_BASE_URL: Final[str] = "http://localhost:11434"
SUPPORTED_PROVIDERS: Final[frozenset[str]] = frozenset({"openai", "ollama"})


class LLMConfigurationError(RuntimeError):
    """Raised when the environment does not describe a usable model."""


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Immutable, validated description of the model to use.

    Attributes:
        provider: Either ``openai`` (covering OpenAI-compatible servers) or ``ollama``.
        model: Provider-specific model identifier.
        api_key: Optional credential; required for the ``openai`` provider.
        base_url: Optional endpoint override for OpenAI-compatible servers.
        temperature: Sampling temperature; ``0`` keeps discovery deterministic.
        timeout_seconds: Per-request timeout enforced by the provider client.
        max_retries: Bounded retry budget handled by the provider client.
    """

    provider: str
    model: str
    api_key: SecretStr | None = None
    base_url: str | None = None
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> LLMConfig:
        """Build a validated configuration from environment variables.

        Args:
            environ: Source mapping; defaults to ``os.environ``.

        Returns:
            The validated configuration.

        Raises:
            LLMConfigurationError: If the provider is unknown, the model name is
                missing, or an ``openai`` provider has no credential.
        """
        env = os.environ if environ is None else environ
        provider = env.get("LLM_PROVIDER", "openai").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
            raise LLMConfigurationError(f"Unsupported LLM_PROVIDER {provider!r}; expected one of: {supported}")

        model = env.get("LLM_MODEL", "").strip()
        if not model:
            raise LLMConfigurationError("LLM_MODEL must name a model, for example 'gpt-5' or 'qwen3'")

        raw_key = env.get("OPENAI_API_KEY") or env.get("LLM_API_KEY")
        api_key = SecretStr(raw_key) if raw_key else None
        if provider == "openai" and api_key is None:
            raise LLMConfigurationError(
                "The 'openai' provider requires OPENAI_API_KEY. Local OpenAI-compatible "
                "servers may use a placeholder value."
            )

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=env.get("LLM_BASE_URL") or None,
        )


class LLMFactory:
    """Creates chat models for the configured provider."""

    @staticmethod
    def create_model(config: LLMConfig | None = None) -> BaseChatModel:
        """Create a fresh chat model instance.

        Args:
            config: Explicit configuration; read from the environment when omitted.

        Returns:
            A LangChain chat model ready for ``ainvoke``.

        Raises:
            LLMConfigurationError: If the configuration is invalid or unsupported.
        """
        active = config if config is not None else LLMConfig.from_env()

        if active.provider == "openai":
            # Serves official OpenAI and any OpenAI-compatible server.
            return ChatOpenAI(
                model=active.model,
                temperature=active.temperature,
                api_key=active.api_key,
                base_url=active.base_url,
                timeout=active.timeout_seconds,
                max_retries=active.max_retries,
            )

        return ChatOllama(
            model=active.model,
            temperature=active.temperature,
            base_url=active.base_url or DEFAULT_OLLAMA_BASE_URL,
        )


def get_llm(config: LLMConfig | None = None) -> BaseChatModel:
    """Return a new chat model for the current call.

    A fresh instance per call keeps provider clients inside the event loop that
    uses them, which is what makes the test suite deterministic.

    Args:
        config: Explicit configuration; read from the environment when omitted.

    Returns:
        A LangChain chat model ready for ``ainvoke``.
    """
    return LLMFactory.create_model(config)

        