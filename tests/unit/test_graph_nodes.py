from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.domain.models import Stage, WorkItem
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState


@pytest.mark.asyncio
async def test_discover_node_updates_state():
    """
    Test that the discover node update the WorkItem stage
    and adds a completion message to the state.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test description",
        stage=Stage.IDLE
    )
    state: AgentState = {"work_item": work_item, "messages": []}
    response = Mock(content='''{
        "repository_id": "owner/repo",
        "languages": [{"name": "Python"}],
        "frameworks": [],
        "architecture_summary": "The repository separates domain models from graph orchestration."
    }''')

    # Act
    # In LangGraph, nodes return a dictionary of field to update
    with (
        patch("aisdlc.graph.nodes.list_files", new=AsyncMock(return_value=[])),
        patch("aisdlc.graph.nodes.get_llm", return_value=Mock(ainvoke=AsyncMock(return_value=response))),
    ):
        update = await discover(state)

    # Assert
    assert update["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL

    assert len(update["messages"]) > 0
    assert "Discovery completed for owner/repo." in update["messages"]
