from aisdlc.domain.models import Stage
from aisdlc.graph.state import AgentState

# Maps a Domain Stage to a LangGraph Node name
# This is the only place where the mapping is defined
STAGE_TO_NODE = {
    Stage.IDLE: "discover",
    Stage.AWAITING_AGENT_PICKUP: "route", # Re-evaluate where to go
    Stage.IN_PROGRESS_BY_AGENT: "human_approval", # Route to human approval after agent work
    Stage.AWAITING_HUMAN_APPROVAL: "human_approval",
    Stage.READY: "discover",
    Stage.DONE: "__end__"
}
def route(state: AgentState) -> str:
    """
    Determines the nex node to visit based on the current state of the WorkItem.
    This is the 'traffic controller' of the LangGraph.
    Uses a mapping table to keep the logic deterministic and easy to extend.
    """
    work_item = state.get("work_item")
    current_stage = work_item.stage if work_item is not None else state.get("stage")

    if current_stage is None:
        raise ValueError("Agent state must contain a work item or stage.")

    return STAGE_TO_NODE.get(current_stage, "discover")