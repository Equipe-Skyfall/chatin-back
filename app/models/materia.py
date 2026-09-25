from typing import TYPE_CHECKING

from sqlalchemy import Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tema import Tema


class Materia(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Matérias (Matemática, Física, ...) are siblings, not a sequence - there is
    no `ordem` here on purpose. Ordering only starts to matter one level down,
    where a tema like 'Álgebra Linear' can genuinely depend on 'Cálculo 1'
    coming first (see `Tema.ordem` / `Modulo.ordem`).

    `owner_user_id` is `NULL` for the global, admin-curated curriculum - a
    non-`NULL` value marks this as a student's own trilha, publicly visible
    and votable by every student (see `app/repositories/voto_repository.py`),
    not private to its owner. Only writing to it is owner-restricted (see
    `app/core/autorizacao.py`); reading is open to everyone, same as the
    global curriculum. `nome` is only unique *within* its own namespace: two
    students (or a student and the global curriculum) can each have an
    "Extensivo ENEM" without colliding - see the partial/composite unique
    indexes below.
    """

    __tablename__ = "materias"
    __table_args__ = (
        Index(
            "uq_materias_nome_global",
            "nome",
            unique=True,
            postgresql_where=text("owner_user_id IS NULL"),
        ),
        UniqueConstraint("owner_user_id", "nome", name="uq_materias_owner_nome"),
    )

    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    # External JWT `userId` claim (same convention as `Conversa.user_id`) -
    # NULL means "global/admin-owned", never a real user.
    owner_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    temas: Mapped[list["Tema"]] = relationship(
        back_populates="materia", cascade="all, delete-orphan", order_by="Tema.ordem"
    )
