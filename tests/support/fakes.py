"""A shared fake provider so the graph tests need not repeat the plumbing.

The Discovery node asks the provider for structured output rather than raw
text, so a fake has to model that call shape. Keeping it in one place stops
each test from inventing its own approximation of the contract.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

from aisdlc.domain.models import DiscoveryReport
from aisdlc.tools.repository import RepositoryListing


def fake_repository_listing(
    repository_id: str,
    *,
    files: tuple[str, ...] = (),
    ref: str = "HEAD",
) -> RepositoryListing:
    """Build the inventory shape ``tools.repository.list_files`` returns."""
    return RepositoryListing(
        repository_id=repository_id, ref=ref, files=files, source="test"
    )


def discovery_report(repository_id: str = "owner/repo") -> DiscoveryReport:
    """Build a valid report for use as fake structured output."""
    return DiscoveryReport(
        repository_id=repository_id,
        languages=[{"name": "Python"}],
        frameworks=[],
        build_system="uv",
        architecture_summary=(
            "The repository separates domain models from graph orchestration."
        ),
        key_components=["src/aisdlc/domain", "src/aisdlc/graph"],
        identified_files=["pyproject.toml"],
    )


def fake_llm_returning(report: DiscoveryReport) -> Mock:
    """A chat model whose structured output resolves to ``report``.

    Args:
        report: The report the fake provider should hand back.

    Returns:
        A mock exposing ``with_structured_output(...).ainvoke(...)``, which
        is the contract the node now depends on.
    """
    structured = Mock(ainvoke=AsyncMock(return_value=report))
    return Mock(with_structured_output=Mock(return_value=structured))


def fake_llm_returning_raw(value: Any) -> Mock:
    """A chat model whose structured output resolves to something invalid.

    Used to prove the node refuses output that is not a DiscoveryReport
    rather than passing a malformed payload downstream (§14).

    Args:
        value: The wrong-typed value the fake provider should return.

    Returns:
        A mock with the same shape as :func:`fake_llm_returning`.
    """
    structured = Mock(ainvoke=AsyncMock(return_value=value))
    return Mock(with_structured_output=Mock(return_value=structured))
