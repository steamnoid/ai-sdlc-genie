"""The Discovery node's orchestration, with both adapters controlled.

No real model and no real GitHub are involved, so the flow stays
deterministic alongside the unit suite (§21). The real-agent counterpart,
which patches nothing, lives in tests/e2e/.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support.fakes import (
    discovery_report,
    fake_llm_returning,
    fake_repository_listing,
)

from aisdlc.domain.models import DiscoveryReport, Stage
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState

#: Fully mocked: no real model, no real network (§21).
pytestmark = pytest.mark.graph


@pytest.mark.asyncio
async def test_discovery_node_maps_structured_output_to_a_report() -> None:
    """Arrange/Act/Assert: the node yields a report and pauses for approval."""
    # Arrange
    repository_id = "owner/repo"
    initial_state: AgentState = {
        "repository_id": repository_id,
        "stage": Stage.IN_PROGRESS_BY_AGENT,
        "discovery_report": None,
        "messages": [],
    }

    # Act
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(
                return_value=fake_repository_listing(repository_id)
            ),
        ),
        patch(
            "aisdlc.graph.nodes.get_llm",
            return_value=fake_llm_returning(discovery_report(repository_id)),
        ),
    ):
        result = await discover(initial_state)

    # Assert
    assert result["stage"] == Stage.AWAITING_HUMAN_APPROVAL

    report = result.get("discovery_report")
    assert report is not None
    assert isinstance(report, DiscoveryReport)
    assert len(report.architecture_summary) > 20
    assert len(report.languages) > 0
