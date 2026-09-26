
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all database models.
    Uses SQLAlchemy 2.0 Declarative style for full type safety.
    """
    pass

class RepositoryModel(Base):
    """
    Database representation of a Github repository.
    Production notes:
    - Composite primary key ensures no duplicate repos for the same owner.
    - Indices are implicitly created for primary keys.
    """