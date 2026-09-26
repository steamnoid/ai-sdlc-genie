from collections.abc import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aisdlc.domain.models import Role, Stage
from aisdlc.domain.models import WorkItem as DomainWorkItem
from aisdlc.persistence.models import WorkItemModel


class WorkItemRepository:
    """
    Production-grade repository for WorkItems.
    Handles the mapping between Database Models and Domain Models.
    """
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
    
    async def create(self, item: DomainWorkItem) -> DomainWorkItem:
        """
        Persists a new WorkItem to the database.
        Maps Domain model -> Database model.
        """
        # Handle repository_id split (e.g. "owner/repo")
        parts = item.repository_id.split("/")
        if len(parts) != 2:
            raise ValueError("repository_id must be in format 'owner/repo'")

        owner, repo_name = parts
        
        # Map Domain -> Database
        db_item = WorkItemModel(
            id=item.id,
            repository_owner=owner,
            repository_name=repo_name,
            title=item.title,
            description=item.description,
            stage=item.stage.value,
            role=item.role.value,
            agent=item.agent,
        )
        self.session.add(db_item)
        await self.session.flush()
        return item

    async def get_by_id(self, item_id: str) -> DomainWorkItem | None:
        """Retrieves a WorkItem and maps it back to a Domain model."""
        query = select(WorkItemModel).where(WorkItemModel.id == item_id)
        result = await self.session.execute(query)
        db_item = result.scalar_one_or_none()
        
        if not db_item:
            return None

        # Map Database -> Domain
        return DomainWorkItem(
            id=db_item.id,
            repository_id=f"{db_item.repository_owner}/{db_item.repository_name}",
            title=db_item.title,
            description=db_item.description,
            stage=Stage(db_item.stage),
            role=Role(db_item.role),
            agent=db_item.agent,
        )

    async def update_stage(self, item_id: str, new_stage: Stage | str, new_agent: str | None) -> None:
        """Updates only the stage and agent for a given WorkItem."""
        stage = Stage(new_stage)
        query = (
            update(WorkItemModel)
            .where(WorkItemModel.id == item_id)
            .values(stage=stage.value, agent=new_agent)
        )
        await self.session.execute(query)

    async def delete(self, item_id: str) -> None:
        """Removes a WorkItem from the database."""
        query = delete(WorkItemModel).where(WorkItemModel.id == item_id)
        await self.session.execute(query)

    async def list_by_repository(self, repository_id: str) -> Sequence[DomainWorkItem]:
        """Return all work items for a given repostory (owner/repo)."""
        owner, repo_name = repository_id.split("/")

        query = select(WorkItemModel).where(
            WorkItemModel.repository_owner == owner,
            WorkItemModel.repository_name == repo_name,
        )
        result = await self.session.execute(query)
        db_items = result.scalars().all()

        return [
            DomainWorkItem(
                id=db_item.id,
                repository_id=f"{db_item.repository_owner}/{db_item.repository_name}",
                title=db_item.title,
                description=db_item.description,
                stage=Stage(db_item.stage),
                role=Role(db_item.role),
                agent=db_item.agent,
            )
            for db_item in db_items
        ]