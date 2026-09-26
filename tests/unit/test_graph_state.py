from aisdlc.domain.models import WorkItem
from aisdlc.graph.state import AgentState


def test_agent_state_initialization():
    """
    Test that AgentState can be initialized with a WorkItem 
    and has the required default fields.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc"
    )
    
    # Act
    state: AgentState = {
        "work_item": work_item,
        "messages": [],
        "next_node": None
    }
    
    # Assert
    assert state["work_item"].id == "item-123"
    assert state["messages"] == []
    assert state["next_node"] is None