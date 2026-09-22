from typing import TYPE_CHECKING
from uuid import UUID as PyUUID

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.materia import Materia


class VotoMateria(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One student's up/down vote on a community-created (`owner_user_id`
    not null) matéria - fully open, no moderation gate (see the product
    decision behind this: votes are the only quality signal). `valor` is
    `+1`/`-1`, never `0` - voting again just updates the existing row
    (upsert on the unique `(user_id, materia_id)` pair) rather than
    accumulating multiple votes from the same student. Never created for a
    global (`owner_user_id IS NULL`) matéria - voting on the official
    curriculum doesn't mean anything; enforced in `voto_service`, not here.
    """

    __tablename__ = "votos_materia"
    __table_args__ = (
        UniqueConstraint("user_id", "materia_id", name="uq_votos_materia_user_materia"),
        CheckConstraint("valor IN (-1, 1)", name="ck_votos_materia_valor"),
    )

    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    materia_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materias.id", ondelete="CASCADE"), nullable=False
    )
    valor: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    materia: Mapped["Materia"] = relationship()
