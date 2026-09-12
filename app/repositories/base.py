"""Repository pattern contract.

Services depend on repositories, never on `Session`/`db.query(...)` directly -
this is what lets `tests/fakes/in_memory_repositories.py` stand in for the real
thing in unit tests with no database at all.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class Repository(ABC, Generic[ModelT]):
    @abstractmethod
    def get(self, entity_id: UUID) -> ModelT | None: ...

    @abstractmethod
    def add(self, entity: ModelT) -> ModelT: ...

    @abstractmethod
    def delete(self, entity: ModelT) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...


class SqlAlchemyRepository(Repository[ModelT]):
    """Generic SQLAlchemy implementation of the base CRUD contract.

    Concrete repositories set `model` and add domain-shaped query methods on
    top (e.g. `list_by_materia`, `get_by_ordem`) - the point of a repository is
    to expose the vocabulary of the domain, not a thin passthrough to the ORM.
    """

    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, entity_id: UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        self.db.delete(entity)

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def flush(self) -> None:
        self.db.flush()

    def refresh(self, entity: ModelT) -> None:
        self.db.refresh(entity)
