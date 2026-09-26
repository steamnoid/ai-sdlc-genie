import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from aisdlc.domain.models import WorkItem, Stage, Role
from aisdlc.persistence.models import Base
from aisdlc.persistence.repository import WorkItemRepository

# Use SQLite in-memory for lightning fast tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def db_session():
    """Fixture to set up a fresh in-memory database for reach test."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        # Crate all tables defined in our Base
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()

@pytest.fixture
def repo(db_session):
    """Provides a WorkItemRepository instance."""
    return WorkItemRepository(db_session)

@pytest.mark.asyncio
async def test_create_and_get_work_item(repo):
    """Test that we can save a WorkItem and retrieve it correctly."""
    # Arrange
    item = WorkItem(
        id="item-1",
        repository_id="owner/repo",
        title="TDD Test",
        description="Testing persistance",
        stage=Stage.IDLE,
        role=Role.AI
    )

    # Act
    await repo.create(item)
    retrieved = await repo.get_by_id("item-1")

    # Assert
    assert retrieved is not None
    assert retrieved.title == "TDD Test"
    assert retrieved.repository_id  == "owner/repo"
    assert retrieved.stage == Stage.IDLE

@pytest.mark.asyncio
async def test_get_non_eistent_item(repo):
    """Test that retrieving a non-existent work item returns None."""
    retrieved = await repo.get_by_id("non-existent-item")
    assert retrieved is None

@pytest.mark.asyncio
async def test_update_stage(repo):
    """Test that updating the stage works as expected."""
    # Arrange
    item = WorkItem(
        id="item-2",
        repository_id="owner/repo",
        title="Update Test",
        description="Testing updates",
        stage=Stage.IDLE,
        role=Role.AI
    )
    await repo.create(item)
    
    # Act
    await repo.update_stage("item-2", Stage.AWAITING_AGENT_PICKUP.value, "agent-007")
    updated = await repo.get_by_id("item-2")
    
    # Assert
    assert updated.stage == Stage.AWAITING_AGENT_PICKUP
    assert updated.agent == "agent-007"

@pytest.mark.asyncio
async def test_list_by_repository(repo):
    """Test retrieving all items for a specific repository."""
    # Arrange: Create two items for repo A and one for repo B
    items = [
        WorkItem(id="1", repository_id="owner/repo-a", title="T1", description="D1"),
        WorkItem(id="2", repository_id="owner/repo-a", title="T2", description="D2"),
        WorkItem(id="3", repository_id="owner/repo-b", title="T3", description="D3"),
    ]
    for i in items:
        await repo.create(i)
        
    # Act
    results = await repo.list_by_repository("owner/repo-a")
    
    # Assert
    assert len(results) == 2
    assert all(item.repository_id == "owner/repo-a" for item in results)