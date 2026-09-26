from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field
from typing import Optional


class Stage(StrEnum):
    IDLE = "IDLE"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    IN_PROGRESS_BY_AGENT = "IN_PROGRESS_BY_AGENT"
    AWAITING_AGENT_PICKUP = "AWAITING_AGENT_PICKUP"
    READY = "READY"
    DONE = "DONE"

class Role(StrEnum):
    PO = "PO"
    DEV = "DEV"
    QA = "QA"
    SEC = "SEC"
    ARCH = "ARCH"
    AI = "AI"

class Repository(BaseModel):
    owner: str
    name: str
    default_branch: str = "main"

class WorkItem(BaseModel):
    id: str
    repository_id: str
    title: str
    description: str
    stage: Stage = Stage.IDLE
    role: Role = Role.AI
    agent: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
