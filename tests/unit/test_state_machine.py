
import pytest

from aisdlc.domain.models import WorkItem, Stage
from aisdlc.domain.state_machine import StateMachineError, transition, validate_state


@pytest.fixture
def basic_work_item():
    """Fixture providing a fresh WorkItem for each test."""
    return WorkItem(
        id="item-123",
        repository_id="repo-456",
        title="Test Task",
        description="Test Description",
    )

def test_legal_transition_success(basic_work_item):
    """Test that a valid transition from IDLE to AWAITING_AGENT_PICKUP succeeds."""
    # Arrange: Start at IDLE (default)
    item = basic_work_item

    # Act: Transition to AWAITING_AGENT_PICKUP
    result = transition(item, Stage.AWAITING_AGENT_PICKUP, agent="test-agent-001")

    # Assert
    assert result.stage == Stage.AWAITING_AGENT_PICKUP
    assert result.id == item.id

def test_illegal_transition_failure(basic_work_item):
    """Test that transitioning from IDLE directly do DONE is forbidden"""
    item = basic_work_item

    # Act & Assert: Should raise StateMachineError
    with pytest.raises(StateMachineError) as excinfo:
        transition(item, Stage.DONE)

    assert "Illegal transition" in str(excinfo.value)

def test_invariant_agent_required_for_pickup(basic_work_item):
    """
    Test that a WorkItem in AWAITING_AGENT_PICKuP must have an agent.
    The transition function should handle this, but we test validate_stae directly.
    """
    item = basic_work_item.model_copy(update={
        "stage": Stage.AWAITING_AGENT_PICKUP,
        "agent": None # Thi violates the invariant
    })

    with pytest.raises(StateMachineError) as excinfo:
        validate_state(item)

    assert "requires an assigned agent" in str(excinfo.value)

def test_invariant_no_agent_for_done(basic_work_item):
    """Test that a WorkItem in DONE stage cannot have an agent."""
    item = basic_work_item.model_copy(update={
        "stage": Stage.DONE,
        "agent": "some-agent"
    })

    with pytest.raises(StateMachineError) as excinfo:
        validate_state(item)

    assert "requires no assigned agent" in str(excinfo.value)

def test_transition_forces_agent_none_done(basic_work_item):
    """Test that transitioning to DONE automatically clears the agent."""
    # Setup: Item is in a staet that has an agent
    item = basic_work_item.model_copy(update={
        "stage": Stage.AWAITING_HUMAN_APPROVAL,
        "agent": "some-agent"
    })

    # Act: Transition to DONE
    result = transition(item, Stage.DONE)

    # Assert: Agent should be cleared
    assert result.stage == Stage.DONE
    assert result.agent is None
    
