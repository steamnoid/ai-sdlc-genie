
# Tabel of legal stage transitions: {Source_Stage: {Target_Stages_Set}}

from aisdlc.domain.models import Stage, WorkItem

LEGAL_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.IDLE: {Stage.AWAITING_AGENT_PICKUP},
    Stage.AWAITING_AGENT_PICKUP: {Stage.IN_PROGRESS_BY_AGENT},
    Stage.IN_PROGRESS_BY_AGENT: {Stage.AWAITING_HUMAN_APPROVAL, Stage.AWAITING_AGENT_PICKUP},
    Stage.AWAITING_HUMAN_APPROVAL: {Stage.AWAITING_AGENT_PICKUP, Stage.DONE},
    Stage.READY: {Stage.AWAITING_AGENT_PICKUP},
    Stage.DONE: set(), # Final Stage
}

class StateMachineError(Exception):
    """Exception raised when an illegal state transition is attempted."""

def validate_state(work_item: WorkItem) -> None:
    """
    Validates state invariants.
    As per requirements:
    - AGENT=None <-> Stage in {IDLE, AWAITING_HUMAN_APPROVAL, READY, DONE}
    - AGENT!=None <-> Stage in {AWAITING_AGENT_PICKUP, IN_PROGRESS_BY_AGENT}
    """
    has_agent = work_item.agent is not None
    stage = work_item.stage

    if not has_agent:
        allowed_stages = {Stage.IDLE, Stage.AWAITING_HUMAN_APPROVAL, Stage.READY, Stage.DONE}
        if stage not in allowed_stages:
            raise StateMachineError(f"Invariant violation: Stage {stage} requires an assigned agent")
    else:
        allowed_stages = {Stage.AWAITING_AGENT_PICKUP, Stage.IN_PROGRESS_BY_AGENT}
        if stage not in allowed_stages:
            raise StateMachineError(f"Invariant violation: Stage {stage} requires no assigned agent")

def transition(work_item: WorkItem, requested_stage: Stage, agent: str | None = None) -> WorkItem:
    """
    Attempts to transition the WorkItem to a new stage.
    If the transition is illegal, raises StateMachineError.
    Returns a new copy of the WorkItem (immutaibility pattern).
    """
    current_stage = work_item.stage

    # 1. Check if the transition is legal according to the transition table
    allowed_destinations = LEGAL_TRANSITIONS.get(current_stage, set())
    if requested_stage not in allowed_destinations:
        raise StateMachineError(
            f"Illegal transition: cannot move from {current_stage} to {requested_stage}."
        )

    # 2. Create a new copy of the object with the updated state (Pydantic model_copy)
    updated_item = work_item.model_copy(update={
        "stage": requested_stage,
        "agent": agent if agent is not None else work_item.agent
    })

    # 3. Enfore agent rules base on the requested stage
    # If transitioning to a stage that MUST NOT have an agent, force it to None
    if requested_stage in {Stage.IDLE, Stage.AWAITING_HUMAN_APPROVAL, Stage.READY, Stage.DONE}:
        updated_item.agent = None

    # 4. Final invariant validation
    validate_state(updated_item)

    return updated_item