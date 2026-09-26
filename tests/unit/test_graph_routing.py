from aisdlc.domain.models import Stage, WorkItem
from aisdlc.graph.router import route
from aisdlc.graph.state import AgentState


def test_route_idle_to_discover():
    """
    Test that the router directs a WorkItem in IDLE stage to the 'discover' node.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc",
        stage=Stage.IDLE
    )
    state = AgentState(work_item=work_item)

    # Act
    next_node = route(state)

    # Assert
    assert next_node == "discover"

def test_route_done_to_end():
    """
    Test that the router directs a WorkItem in DONE stage to the 'end' node of the graph.
    """
    # Arrange
    work_item = WorkItem(
        id="item-123",
        repository_id="owner/repo",
        title="Test Task",
        description="Test desc",
        stage=Stage.DONE
    )
    state = AgentState(work_item=work_item)

    # Act
    next_node = route(state)

    # Assert
    assert next_node == "__end__"