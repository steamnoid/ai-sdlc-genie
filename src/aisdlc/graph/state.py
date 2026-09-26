import operator
from typing import Annotated, NotRequired, TypedDict

from aisdlc.domain.models import DiscoveryReport, Stage, WorkItem


class AgentState(TypedDict, total=False):
    """
    The shared state of the LangGraph orchestration.
    Using TypedDict for compatibility with LangGraph reducers.
    """
    work_item: WorkItem
    repository_id: str
    stage: Stage
    discovery_report: DiscoveryReport | None
    approval_granted: bool | None
    messages: Annotated[list[str], operator.add]
    next_node: NotRequired[str | None]