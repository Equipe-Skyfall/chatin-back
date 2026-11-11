from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResumoAluno(Base):
    """A running summary of everything a student has discussed with the
    teacher, across all their conversations. It is what the student chat hands
    the model as context instead of the whole history (see
    `chat_aluno_service`), refreshed as the conversations grow.

    `mensagens_resumidas` maps a conversa id to how many of its messages are
    already folded into `resumo`, so a refresh only sends the new ones - and a
    student switching between conversations never loses a stretch of either.
    """

    __tablename__ = "resumos_aluno"

    # From the external auth service's JWT `userId` claim (cuid string).
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    resumo: Mapped[str] = mapped_column(Text, nullable=False)
    mensagens_resumidas: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
