import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class TrilhaEstudando(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The student chose to study a community trilha (someone else's matéria).

    Only adoptions are stored: the global (verified) curriculum is for everyone
    and a student's own trilhas are theirs by `Materia.owner_user_id`, so
    neither needs a row. Together the three make up "the trilhas this student
    studies" (see `MateriaRepository.list_globais_e_estudando_*`).
    """

    __tablename__ = "trilhas_estudando"
    __table_args__ = (UniqueConstraint("user_id", "materia_id", name="uq_trilha_estudando"),)

    # From the external auth service's JWT `userId` claim (cuid string).
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    materia_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materias.id", ondelete="CASCADE"), nullable=False
    )
