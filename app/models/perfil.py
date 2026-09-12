from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerfilUsuario(Base):
    """A local mirror of just enough authSys user data to show a name instead
    of a bare cuid in the ranking (see `app.routers.xp`) - this service has no
    other access to user profile data, since auth/user records live entirely
    in authSys. Kept fresh opportunistically: every authenticated request
    upserts this row from that request's own JWT claims (see
    `app.deps._sincronizar_perfil`), not via any sync job or call to authSys.
    """

    __tablename__ = "perfis_usuario"

    # From the external auth service's JWT `userId` claim - a Prisma cuid()
    # string, not a UUID.
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
