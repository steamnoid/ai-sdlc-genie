"""The graph executes its first slice and pauses at the approval boundary.

The model and the GitHub tool are both faked, so this exercises the real
LangGraph wiring with no network and no model (§21).
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

from aisdlc.domain.models import Stage, WorkItem
from aisdlc.graph.workflow import app

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_graph_initial_flow() -> None:
    """Arrange/Act/Assert: START → discover → router, then the graph pauses.

    The compiled graph uses interrupt_before=["human_approval"], so the run
    must stop with the work item awaiting a human and must not have run
    the approval node itself.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc",
        stage=Stage.IDLE,
    )
    initial_state = {
        "work_item": work_item,
        "messages": [],
    }

    # Act
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch(
            "aisdlc.graph.nodes.get_llm",
            return_value=fake_llm_returning(discovery_report()),
        ),
    ):
        final_state = await app.ainvoke(initial_state)

    # Assert
    assert final_state["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL
    assert any("discovery completed" in msg.lower() for msg in final_state["messages"])
