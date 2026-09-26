"""The Discovery node must produce a validated report and advance the stage.

Both external adapters are patched at the module boundary, so this proves
the node's orchestration with no real model and no real GitHub (§21). The
real-agent counterpart lives in tests/e2e/.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support.fakes import (
    discovery_report,
    fake_llm_failing_methods,
    fake_llm_returning,
    fake_llm_returning_raw,
    fake_repository_listing,
)

from aisdlc.domain.models import DiscoveryReport, Stage, WorkItem
from aisdlc.graph.nodes import discover
from aisdlc.graph.state import AgentState

pytestmark = pytest.mark.asyncio


def _state() -> AgentState:
    """Build the state the graph would hold when discovery starts."""
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test description",
        stage=Stage.IDLE,
    )
    return {"work_item": work_item, "messages": []}


async def test_discover_node_maps_structured_output_to_a_report() -> None:
    """Arrange/Act/Assert: validated output becomes the node's report.

    The node now relies on LangChain structured output, so the contract
    under test is that a DiscoveryReport comes back and the work item
    advances to the human-approval boundary.
    """
    # Arrange
    report = discovery_report()

    # Act
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=fake_llm_returning(report)),
    ):
        update = await discover(_state())

    # Assert
    assert update["discovery_report"] is report
    assert update["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL
    assert "Discovery completed for owner/repo." in update["messages"]


async def test_discover_node_rejects_structured_output_of_the_wrong_type() -> None:
    """Arrange/Act/Assert: a malformed provider result is never accepted.

    §14 forbids silently accepting malformed model output, so a provider
    that hands back something other than a DiscoveryReport must fail
    loudly rather than reaching downstream agents.
    """
    # Arrange
    wrong = {"architecture_summary": "not a DiscoveryReport"}

    # Act / Assert
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=fake_llm_returning_raw(wrong)),
        pytest.raises(TypeError, match="not a DiscoveryReport"),
    ):
        await discover(_state())


async def test_discover_node_pins_the_report_to_the_analysed_repository() -> None:
    """Arrange/Act/Assert: the report cannot claim a different repository.

    The model is told which repository it is looking at, but a report
    naming a different one would silently misattribute groundedness.
    """
    # Arrange: the provider echoes the wrong repository id
    report = discovery_report("someone/else")

    # Act
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=fake_llm_returning(report)),
    ):
        update = await discover(_state())

    # Assert
    result = update["discovery_report"]
    assert isinstance(result, DiscoveryReport)
    assert result.repository_id == "owner/repo"


async def test_discover_node_falls_back_when_the_provider_rejects_a_method() -> None:
    """Arrange/Act/Assert: an unsupported method does not fail the agent.

    §29 requires the same graph to serve a cloud model and a local model
    with no agent rewrite. Measured against real providers, `json_schema`
    fails on https://ollama.com/v1 and `function_calling` fails against a
    local Ollama, so binding to one method cannot satisfy §29. The node
    must try the alternatives instead.
    """
    # Arrange: the provider refuses function_calling but honours json_schema
    report = discovery_report()
    llm = fake_llm_failing_methods(
        working_method="json_schema",
        report=report,
        failing_methods=("function_calling",),
    )

    # Act
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=llm),
    ):
        update = await discover(_state())

    # Assert
    assert update["discovery_report"] is report


async def test_discover_node_reports_every_method_it_tried() -> None:
    """Arrange/Act/Assert: total failure names what was attempted.

    A silent fallback to nothing, or a bare "discovery failed", leaves the
    next engineer unable to tell a provider problem from a prompt problem.
    """
    # Arrange: the provider refuses every method
    llm = fake_llm_failing_methods(
        working_method="never",
        report=discovery_report(),
        failing_methods=("function_calling", "json_schema", "json_mode"),
    )

    # Act / Assert
    with (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch("aisdlc.graph.nodes.get_llm", return_value=llm),
        pytest.raises(RuntimeError) as excinfo,
    ):
        await discover(_state())

    message = str(excinfo.value)
    assert "function_calling" in message
    assert "json_schema" in message
