"""The discovery node's effect on the work item and the message list.

Both external adapters are patched at the module boundary, so no real model
or network is involved (§21).
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
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_discover_node_updates_state() -> None:
    """Arrange/Act/Assert: the node advances the stage and logs completion.

    In LangGraph a node returns a dict of field updates, so the assertion
    is on the returned updates rather than on mutated state.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test description",
        stage=Stage.IDLE,
    )
    state: AgentState = {"work_item": work_item, "messages": []}

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
        update = await discover(state)

    # Assert
    assert update["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL
    assert len(update["messages"]) > 0
    assert "Discovery completed for owner/repo." in update["messages"]
