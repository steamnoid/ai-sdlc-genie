"""RED — an approved work item must be able to leave the approval gate.

§11 requires the workflow to be resumable after approval, and §8 defines
AWAITING_HUMAN_APPROVAL → READY and → DONE as legal transitions. The
graph has neither: `human_approval` is a node with no outgoing edge, so
the compiled graph terminates there and the remaining eight agents of §10
are unreachable.

These tests drive the compiled graph, with both external adapters faked, so
the defect is the graph's wiring rather than a model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support.fakes import (  # noqa: E402
    discovery_report,
    fake_llm_returning,
    fake_repository_listing,
)

from aisdlc.domain.models import Stage, WorkItem
from aisdlc.graph.workflow import app

pytestmark = pytest.mark.graph


def _initial_state() -> dict:
    """Build the state the graph starts from, before discovery."""
    return {
        "work_item": WorkItem(
            id="item-123",
            repository_id="owner/repo",
            title="Test Task",
            description="Test desc",
            stage=Stage.IDLE,
        ),
        "messages": [],
    }


def _patch_adapters():
    """Fake the model and the GitHub tool for the discovery node."""
    return (
        patch(
            "aisdlc.graph.nodes.list_files",
            new=AsyncMock(return_value=fake_repository_listing("owner/repo")),
        ),
        patch(
            "aisdlc.graph.nodes.get_llm",
            return_value=fake_llm_returning(discovery_report()),
        ),
    )


@pytest.mark.asyncio
async def test_graph_pauses_at_the_approval_gate() -> None:
    """Arrange/Act/Assert: the first run stops awaiting a human.

    This is the interrupt boundary and it already works. It is pinned so
    the resumption test below has something to resume from.
    """
    # Act
    with _patch_adapters()[0], _patch_adapters()[1]:
        paused = await app.ainvoke(_initial_state())

    # Assert
    assert paused["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL


@pytest.mark.asyncio
async def test_graph_resumes_and_reaches_ready_after_approval() -> None:
    """Arrange/Act/Assert: granting approval advances the work item to READY.

    §8 makes AWAITING_HUMAN_APPROVAL → READY legal and §11 makes
    resumption mandatory. Today the graph has no edge out of the approval
    node, so the second invoke has nowhere to go and the stage never
    leaves AWAITING_HUMAN_APPROVAL.
    """
    # Arrange: run to the interrupt, then approve and resume
    config = {"configurable": {"thread_id": "test-approval-resume"}}
    with _patch_adapters()[0], _patch_adapters()[1]:
        paused = await app.ainvoke(_initial_state(), config)
        assert paused["work_item"].stage == Stage.AWAITING_HUMAN_APPROVAL

        resumed = await app.ainvoke(
            {**paused, "approval_granted": True},
            config,
        )

    # Assert
    assert resumed["work_item"].stage == Stage.READY


@pytest.mark.asyncio
async def test_graph_stops_at_the_end_after_completion() -> None:
    """Arrange/Act/Assert: reaching DONE terminates the graph (§8).

    DONE is terminal with no outgoing edge, so the router must send the
    run to __end__ rather than starting another node.
    """
    # Arrange
    config = {"configurable": {"thread_id": "test-done-terminal"}}
    with _patch_adapters()[0], _patch_adapters()[1]:
        paused = await app.ainvoke(_initial_state(), config)

        # Act: approve and ask for completion in one step
        resumed = await app.ainvoke(
            {**paused, "approval_granted": True, "mark_complete": True},
            config,
        )

    # Assert
    assert resumed["work_item"].stage == Stage.DONE
    assert resumed["next_node"] == "__end__"
