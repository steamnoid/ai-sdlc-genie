from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.domain.models import DiscoveryReport, Stage
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState


@pytest.mark.asyncio
async def test_discovery_agent_e2e_flow():
    """
    End-to-end test for the Discovery Agent orchestration.
    External GitHub and LLM adapters are controlled so the workflow remains
    deterministic and can run alongside unit tests.
    """
    # Arrange
    test_repo = "steamnoid/ai-sdlc-genie" 
    initial_state: AgentState = {
        "repository_id": test_repo,
        "stage": Stage.IN_PROGRESS_BY_AGENT,
        "discovery_report": None,
        "messages": []
    }
    
    response = Mock(content='''{
        "repository_id": "steamnoid/ai-sdlc-genie",
        "languages": [{"name": "Python"}],
        "frameworks": [{"name": "LangGraph", "purpose": "orchestration"}],
        "build_system": "uv",
        "architecture_summary": "The application separates domain state, graph orchestration, and external adapters.",
        "key_components": ["domain", "graph", "tools"]
    }''')

    with (
        patch("aisdlc.graph.nodes.list_files", new=AsyncMock(return_value=["pyproject.toml"])),
        patch("aisdlc.graph.nodes.read_file", new=AsyncMock(return_value="[project]\nname = 'aisdlc'")),
        patch("aisdlc.graph.nodes.get_llm", return_value=Mock(ainvoke=AsyncMock(return_value=response))),
    ):
        result = await discover(initial_state)

    assert result["stage"] == Stage.AWAITING_HUMAN_APPROVAL

    report = result.get("discovery_report")
    assert report is not None
    assert isinstance(report, DiscoveryReport)
    assert len(report.architecture_summary) > 20
    assert len(report.languages) > 0