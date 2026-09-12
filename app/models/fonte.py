import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tema import Tema

TIPO_BUSCA_AUTOMATICA = "busca_automatica"


class Fonte(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "fontes"

    tema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("temas.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default=TIPO_BUSCA_AUTOMATICA)
    origem: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo_extraido: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    tema: Mapped["Tema"] = relationship(back_populates="fontes")
