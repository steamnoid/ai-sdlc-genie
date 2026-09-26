from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.domain.models import DiscoveryReport, Stage
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState
from aisdlc.tools.repository import RepositoryListing

#: Fully mocked: no real model, no real GitHub (§21). The real-agent version
#: of this flow lives in tests/e2e/.
pytestmark = pytest.mark.graph


@pytest.mark.asyncio
async def test_discovery_node_maps_raw_output_to_report():
    """
    Test the Discovery node's orchestration with both external adapters
    controlled, so the flow stays deterministic alongside the unit tests.
    """
    # Arrange
    repository_id = "owner/repo"
    initial_state: AgentState = {
        "repository_id": repository_id,
        "stage": Stage.IN_PROGRESS_BY_AGENT,
        "discovery_report": None,
        "messages": [],
    }

    response = Mock(content=f'''{{
        "repository_id": "{repository_id}",
        "languages": [{{"name": "Python"}}],
        "frameworks": [{{"name": "LangGraph", "purpose": "orchestration"}}],
        "build_system": "uv",
        "architecture_summary": "The application separates domain state, graph orchestration, and external adapters.",
        "key_components": ["domain", "graph", "tools"]
    }}''')

    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(
                return_value=RepositoryListing(
                    repository_id=repository_id, ref="HEAD", files=(), source="test"
                )
            ),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=Mock(ainvoke=AsyncMock(return_value=response))),
    ):
        result = await discover(initial_state)

    # Assert: the node moved the stage and produced a validated report
    assert result["stage"] == Stage.AWAITING_HUMAN_APPROVAL

    report = result.get("discovery_report")
    assert report is not None
    assert isinstance(report, DiscoveryReport)
    assert len(report.architecture_summary) > 20
    assert len(report.languages) > 0