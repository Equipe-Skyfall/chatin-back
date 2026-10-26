from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class IaConsumo(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One call to the AI provider (RNF7) - each retry attempt is its own row,
    since each one is billed. Written best-effort by `app/ai/consumo.py`: losing
    a row must never break the request that made the call, so nothing here
    holds a foreign key (a user or módulo can disappear without touching the
    usage history) and `user_id` is null for work done with no logged-in user
    (e.g. background content generation)."""

    __tablename__ = "ia_consumo"

    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # The `AIProvider` method that made the call (`conversar_com_agente_aluno`...).
    operacao: Mapped[str] = mapped_column(String(80), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # `TipoFalhaIA` value when `sucesso` is false.
    tipo_falha: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Null when the provider did not report usage for the call.
    tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_saida: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Model round-trips inside the call (an agent may loop over its tools).
    chamadas_modelo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False)
