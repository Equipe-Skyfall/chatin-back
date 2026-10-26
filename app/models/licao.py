import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class LicaoIniciada(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The student already received the opening lesson for a módulo.

    Per user because `Modulo` is shared curriculum. A row here is the
    `start_lesson` flag: it unlocks the módulo's quiz.
    """

    __tablename__ = "licoes_iniciadas"
    __table_args__ = (UniqueConstraint("user_id", "modulo_id", name="uq_licao_iniciada_modulo"),)

    # From the external auth service's JWT `userId` claim (cuid string).
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    modulo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modulos.id", ondelete="CASCADE"), nullable=False
    )
