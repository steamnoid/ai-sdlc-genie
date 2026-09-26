from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.domain.models import DiscoveryReport, Stage, WorkItem
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState


@pytest.mark.asyncio
async def test_discover_node_produces_report():
    """
    Test that the discover node produces a structured DiscoveryReport
    and update the state correctly.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc",
        stage=Stage.IDLE
    )
    state: AgentState = {"work_item": work_item, "messages": []}
    response = Mock(content='''{
        "repository_id": "owner/repo",
        "languages": [{"name": "Python"}],
        "frameworks": [],
        "build_system": "uv",
        "architecture_summary": "A package organized around explicit domain and graph layers."
    }''')

    # Act
    with (
        patch("aisdlc.graph.nodes.list_files", new=AsyncMock(return_value=["pyproject.toml"])),
        patch("aisdlc.graph.nodes.read_file", new=AsyncMock(return_value="[project]")),
        patch("aisdlc.graph.nodes.get_llm", return_value=Mock(ainvoke=AsyncMock(return_value=response))),
    ):
        update = await discover(state)

    # Assert
    assert "discovery_report" in update
    report = update["discovery_report"]
    assert isinstance(report, DiscoveryReport)

    assert len(report.languages) > 0
    assert report.build_system is not None
    assert update["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL