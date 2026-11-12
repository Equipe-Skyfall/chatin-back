from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ApelidoEmUsoException
from app.db.session import DbSession
from app.models.perfil import PerfilUsuario
from app.repositories.base import SqlAlchemyRepository


class PerfilRepository(SqlAlchemyRepository[PerfilUsuario]):
    model = PerfilUsuario

    def upsert(self, user_id: str, nome: str | None, email: str | None) -> None:
        """One statement, one round trip: insert on first sight, update only
        when something actually changed (`IS DISTINCT FROM` short-circuits the
        write on Postgres' side for the very common case of an unchanged
        profile) - safe to call on every authenticated request without it
        turning into a write-heavy hot path."""
        stmt = insert(PerfilUsuario).values(user_id=user_id, nome=nome, email=email)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PerfilUsuario.user_id],
            set_={"nome": stmt.excluded.nome, "email": stmt.excluded.email},
            where=(PerfilUsuario.nome.is_distinct_from(stmt.excluded.nome))
            | (PerfilUsuario.email.is_distinct_from(stmt.excluded.email)),
        )
        self.db.execute(stmt)
        self.db.commit()

    def nomes_por_ids(self, user_ids: list[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        stmt = select(PerfilUsuario.user_id, PerfilUsuario.nome).where(
            PerfilUsuario.user_id.in_(user_ids)
        )
        return {row.user_id: row.nome for row in self.db.execute(stmt) if row.nome}

    def apelidos_por_ids(self, user_ids: list[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        stmt = select(PerfilUsuario.user_id, PerfilUsuario.apelido).where(
            PerfilUsuario.user_id.in_(user_ids)
        )
        return {row.user_id: row.apelido for row in self.db.execute(stmt) if row.apelido}

    def apelido_de(self, user_id: str) -> str | None:
        return self.db.execute(
            select(PerfilUsuario.apelido).where(PerfilUsuario.user_id == user_id)
        ).scalar_one_or_none()

    def definir_apelido(self, user_id: str, apelido: str) -> None:
        """Raises `ApelidoEmUsoException` when another student already has it
        (case-insensitive) - checked up front for the friendly path, and again
        through the unique index for the race between two simultaneous saves."""
        em_uso = self.db.execute(
            select(PerfilUsuario.user_id).where(
                func.lower(PerfilUsuario.apelido) == apelido.lower(),
                PerfilUsuario.user_id != user_id,
            )
        ).first()
        if em_uso is not None:
            raise ApelidoEmUsoException()
        perfil = self.db.get(PerfilUsuario, user_id)
        if perfil is None:
            perfil = PerfilUsuario(user_id=user_id)
            self.db.add(perfil)
        perfil.apelido = apelido
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ApelidoEmUsoException() from None


def get_perfil_repository(db: DbSession) -> PerfilRepository:
    return PerfilRepository(db)


PerfilRepo = Annotated[PerfilRepository, Depends(get_perfil_repository)]
