from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    agent: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LanguageInfo(BaseModel):
    name: str
    version: str | None = None
    description: str | None = None

class FrameworkInfo(BaseModel):
    name: str
    purpose: str | None = None
    description: str | None = None

class DiscoveryReport(BaseModel):
    """
    Structured output of the Repository Discovery Agent.
    Complies with Section 10 of the system instructions.
    """
    model_config = ConfigDict(frozen=True)
    
    repository_id: str
    languages: list[LanguageInfo] = Field(default_factory=list, description="Primary programming languages identified")
    frameworks: list[FrameworkInfo] = Field(default_factory=list, description="Frameworks and major libraries used")
    build_system: str | None = Field(None, description="Build system (e.g., uv, maven, npm)")
    ci_system: str | None = Field(None, description="CI system identified (e.g., GitHub Actions, Jenkins)")
    architecture_summary: str = Field(..., description="High-level summary of the repository architecture")
    key_components: list[str] = Field(default_factory=list, description="List of main modules or components")
    identified_files: list[str] = Field(default_factory=list, description="Crucial files identified during discovery")
    suggested_changes: list[str] = Field(default_factory=list, description="Initial thoughts on potential improvements")