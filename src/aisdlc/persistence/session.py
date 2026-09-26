import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# We fetch DB crednetial from environment variables for production security
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/aisdlc"
)

class DatabaseSessionManager:
    """
    Handles asynchronous database connectionds and sessions.
    Production notes:
    - Uses AsyncEngine for non-blocking I/O.
    - Implements connection pooling vira create_async_engine.
    """
    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_async_engine(
            db_url,
            echo=False, # Set to True only for debugging SQL
            pool_size=10, # Max permanent connections
            max_overflow=20, # Max temporary connections during spikes
            pool_recycle=3600, # Recyce connections every hour to avoid stale sockers
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False, # Prevents accesing expired objects after commit
            class_=AsyncSession
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async context manager to provide a database session.
        Ensure the session is closed automatically.
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Closes the engine connection pool."""
        await self.engine.dispose()

# Global singleton for the application
db_manager = DatabaseSessionManager()