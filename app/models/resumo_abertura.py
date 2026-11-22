import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class ResumoAbertura(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One time a student opened a study summary in the Biblioteca (US18).
    Every opening is its own row - opening the same summary again counts again -
    and downloading the PDF is not an opening. No foreign key to the summary:
    the count is a history, so it must survive the summary being deleted."""

    __tablename__ = "resumo_aberturas"

    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resumo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
