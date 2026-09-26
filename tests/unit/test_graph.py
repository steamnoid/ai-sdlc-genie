from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.domain.models import Stage, WorkItem
from aisdlc.graph.workflow import app


@pytest.mark.asyncio
async def test_graph_initial_flow():
    """
    Test the first slice of the graph:
    START -> DISCOVER -> ROUTER -> HUMAN_APPROVAL
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc",
        stage=Stage.IDLE
    )
    initial_state = {
        "work_item": work_item,
        "messages": []
    }
    response = Mock(content='''{
        "repository_id": "owner/repo",
        "languages": [{"name": "Python"}],
        "frameworks": [],
        "architecture_summary": "The graph coordinates repository discovery through typed state."
    }''')

    # Act
    # The graph pauses at the explicit human-approval boundary.
    with (
        patch("aisdlc.graph.nodes.list_files", new=AsyncMock(return_value=[])),
        patch("aisdlc.graph.nodes.get_llm", return_value=Mock(ainvoke=AsyncMock(return_value=response))),
    ):
        final_state = await app.ainvoke(initial_state)

    # Assert
    assert final_state["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL
    assert any("discovery completed" in msg.lower() for msg in final_state["messages"])