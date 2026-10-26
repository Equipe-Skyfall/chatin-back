import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy import and_, exists, func, or_, select, union
from sqlalchemy.orm import Session

from app.db.session import DbSession
from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.modulo import Modulo
from app.models.perfil import PerfilUsuario
from app.models.progresso import ProgressoUsuario
from app.models.tema import Tema
from app.models.trilha_estudando import TrilhaEstudando
from app.models.voto_materia import VotoMateria

Origem = Literal["todas", "verificadas", "comunidade"]
Ordem = Literal["recentes", "votos", "alunos"]


@dataclass(frozen=True)
class ItemExplorar:
    materia: Materia
    autor_nome: str | None
    temas: int
    modulos: int
    alunos: int
    votos: int
    meu_voto: int | None
    estudando: bool
    propria: bool
    pronta: bool


class TrilhaExplorarRepository:
    """Read-only listing for "Explorar trilhas". Every number comes from a
    grouped sub-query joined once, so a page costs a fixed handful of queries
    however many trilhas it holds (no N+1)."""

    def __init__(self, db: Session):
        self.db = db

    def _stats(self):
        modulos_prontos = (
            select(
                Tema.materia_id.label("materia_id"),
                func.count(func.distinct(Tema.id)).label("temas"),
                func.count(Modulo.id).label("modulos"),
            )
            .join(Modulo, Modulo.tema_id == Tema.id)
            .where(Modulo.status == MODULO_STATUS_PRONTO)
            .group_by(Tema.materia_id)
            .subquery()
        )
        # Who studies a trilha: adopted it, has progress in it, or created it.
        participantes = union(
            select(
                TrilhaEstudando.materia_id.label("materia_id"),
                TrilhaEstudando.user_id.label("user_id"),
            ),
            select(Tema.materia_id, ProgressoUsuario.user_id)
            .join(Modulo, Modulo.tema_id == Tema.id)
            .join(ProgressoUsuario, ProgressoUsuario.modulo_id == Modulo.id),
            select(Materia.id, Materia.owner_user_id).where(Materia.owner_user_id.is_not(None)),
        ).subquery()
        alunos = (
            select(
                participantes.c.materia_id.label("materia_id"),
                func.count(func.distinct(participantes.c.user_id)).label("alunos"),
            )
            .group_by(participantes.c.materia_id)
            .subquery()
        )
        votos = (
            select(
                VotoMateria.materia_id.label("materia_id"),
                func.sum(VotoMateria.valor).label("votos"),
            )
            .group_by(VotoMateria.materia_id)
            .subquery()
        )
        return modulos_prontos, alunos, votos

    def listar(
        self,
        user_id: str,
        origem: Origem,
        ordem: Ordem,
        limite: int,
        offset: int,
    ) -> list[ItemExplorar]:
        modulos_prontos, alunos, votos = self._stats()
        meu_voto = (
            select(VotoMateria.materia_id.label("materia_id"), VotoMateria.valor.label("valor"))
            .where(VotoMateria.user_id == user_id)
            .subquery()
        )
        adotada = exists().where(
            and_(TrilhaEstudando.materia_id == Materia.id, TrilhaEstudando.user_id == user_id)
        )
        n_modulos = func.coalesce(modulos_prontos.c.modulos, 0)
        n_votos = func.coalesce(votos.c.votos, 0)
        n_alunos = func.coalesce(alunos.c.alunos, 0)

        stmt = (
            select(
                Materia,
                PerfilUsuario.nome,
                func.coalesce(modulos_prontos.c.temas, 0),
                n_modulos,
                n_alunos,
                n_votos,
                meu_voto.c.valor,
                adotada,
            )
            .outerjoin(modulos_prontos, modulos_prontos.c.materia_id == Materia.id)
            .outerjoin(alunos, alunos.c.materia_id == Materia.id)
            .outerjoin(votos, votos.c.materia_id == Materia.id)
            .outerjoin(meu_voto, meu_voto.c.materia_id == Materia.id)
            .outerjoin(PerfilUsuario, PerfilUsuario.user_id == Materia.owner_user_id)
            # Only trilhas that already have something to study; the student's
            # own always show so they can follow a trilha still being generated.
            .where(or_(n_modulos > 0, Materia.owner_user_id == user_id))
        )
        if origem == "verificadas":
            stmt = stmt.where(Materia.owner_user_id.is_(None))
        elif origem == "comunidade":
            stmt = stmt.where(Materia.owner_user_id.is_not(None))

        ordenacao = {
            "recentes": (Materia.created_at.desc(),),
            "votos": (n_votos.desc(), n_alunos.desc()),
            "alunos": (n_alunos.desc(), n_votos.desc()),
        }[ordem]
        stmt = stmt.order_by(*ordenacao, Materia.nome).limit(limite).offset(offset)

        itens = []
        for materia, autor, temas, modulos, n_al, n_vo, voto, foi_adotada in self.db.execute(stmt):
            itens.append(
                ItemExplorar(
                    materia=materia,
                    autor_nome=autor if materia.owner_user_id is not None else None,
                    temas=int(temas),
                    modulos=int(modulos),
                    alunos=int(n_al),
                    votos=int(n_vo),
                    meu_voto=int(voto) if voto is not None else None,
                    estudando=bool(
                        materia.owner_user_id is None
                        or materia.owner_user_id == user_id
                        or foi_adotada
                    ),
                    propria=materia.owner_user_id == user_id,
                    pronta=int(modulos) > 0,
                )
            )
        return itens

    def obter(self, user_id: str, materia_id: uuid.UUID) -> ItemExplorar | None:
        """One trilha with the same numbers as `listar`, regardless of whether it
        has ready módulos yet."""
        modulos_prontos, alunos, votos = self._stats()
        meu_voto = (
            select(VotoMateria.valor)
            .where(VotoMateria.user_id == user_id, VotoMateria.materia_id == materia_id)
            .scalar_subquery()
        )
        adotada = exists().where(
            and_(TrilhaEstudando.materia_id == Materia.id, TrilhaEstudando.user_id == user_id)
        )
        stmt = (
            select(
                Materia,
                PerfilUsuario.nome,
                func.coalesce(modulos_prontos.c.temas, 0),
                func.coalesce(modulos_prontos.c.modulos, 0),
                func.coalesce(alunos.c.alunos, 0),
                func.coalesce(votos.c.votos, 0),
                meu_voto,
                adotada,
            )
            .outerjoin(modulos_prontos, modulos_prontos.c.materia_id == Materia.id)
            .outerjoin(alunos, alunos.c.materia_id == Materia.id)
            .outerjoin(votos, votos.c.materia_id == Materia.id)
            .outerjoin(PerfilUsuario, PerfilUsuario.user_id == Materia.owner_user_id)
            .where(Materia.id == materia_id)
        )
        linha = self.db.execute(stmt).first()
        if linha is None:
            return None
        materia, autor, temas, modulos, n_al, n_vo, voto, foi_adotada = linha
        return ItemExplorar(
            materia=materia,
            autor_nome=autor if materia.owner_user_id is not None else None,
            temas=int(temas),
            modulos=int(modulos),
            alunos=int(n_al),
            votos=int(n_vo),
            meu_voto=int(voto) if voto is not None else None,
            estudando=bool(
                materia.owner_user_id is None or materia.owner_user_id == user_id or foi_adotada
            ),
            propria=materia.owner_user_id == user_id,
            pronta=int(modulos) > 0,
        )


def get_trilha_explorar_repository(db: DbSession) -> TrilhaExplorarRepository:
    return TrilhaExplorarRepository(db)


TrilhaExplorarRepo = Annotated[TrilhaExplorarRepository, Depends(get_trilha_explorar_repository)]
