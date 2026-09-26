
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all database models.
    Uses SQLAlchemy 2.0 Declarative style for full type safety.
    """

class RepositoryModel(Base):
    """
    Database representation of a Github repository.
    Production notes:
    - Composite primary key ensures no duplicate repos for the same owner.
    - Indices are implicitly created for primary keys.
    """
    __tablename__ = "repositories"

    owner: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    default_branch: Mapped[str] = mapped_column(String(100), server_default=text("'main'"))

    def __repr__(self) -> str:
        return f"<RepositoryModel(owner={self.owner}, name={self.name})>"

class WorkItemModel(Base):
    """
    Database representation of a work item.
    Production notes:
    - indexed columns for high-performance lookups.
    - explicit foreign keys to ensure referential integrity.
    """
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Foreign keys to RepositoryModel
    repository_owner: Mapped[str] = mapped_column(ForeignKey("repositories.owner", ondelete="CASCADE"))
    repository_name: Mapped[str] = mapped_column(ForeignKey("repositories.name", ondelete="CASCADE"))

    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(String) # text type

    # Store enums as strings for portability and easy debugging
    stage: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(50), index=True)
    agent: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    # Precise timestamps with UTC enforcement
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Index for performance: searching for all items assigned to a specific agent in a specific stage
    __table_args__ = (
        Index("ix_workitem_agent_stage", "agent", "stage"),
    )

    def __repr__(self) -> str:
        return f"<WorkItemModel(id={self.id}, stage={self.stage}, role={self.role}, agent={self.agent})>"