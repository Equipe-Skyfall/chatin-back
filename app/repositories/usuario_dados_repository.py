import logging
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError

from app.db.session import DbSession
from app.models.conversa import Conversa, Mensagem
from app.models.ia_consumo import IaConsumo
from app.models.licao import LicaoIniciada
from app.models.materia import Materia
from app.models.perfil import PerfilUsuario
from app.models.progresso import ProgressoUsuario
from app.models.resumo_abertura import ResumoAbertura
from app.models.resumo_aluno import ResumoAluno
from app.models.resumo_estudo import ResumoEstudo
from app.models.streak import StreakUsuario
from app.models.tentativa import RespostaTentativa, Tentativa, TentativaQuestao
from app.models.trilha_estudando import TrilhaEstudando
from app.models.voto_materia import VotoMateria
from app.models.xp import XpEvento
from app.repositories.base import SqlAlchemyRepository

logger = logging.getLogger(__name__)

ADK_APP_NAME = "chatin"  # `app_name` of the ADK sessions (see `AdkProvider`)


class UsuarioDadosRepository(SqlAlchemyRepository[PerfilUsuario]):
    """Everything this service keeps about one user. There is no users table
    here (authSys owns accounts), so nothing cascades when an account is deleted
    there - this is how the leftovers are removed."""

    model = PerfilUsuario

    def apagar_tudo(self, user_id: str) -> dict[str, int]:
        """Deletes the user's rows from every table, children first, and returns
        how many went from each (tables with none are left out). Does not
        commit: the caller decides."""
        conversas = select(Conversa.id).where(Conversa.user_id == user_id)
        tentativas = select(Tentativa.id).where(Tentativa.user_id == user_id)
        etapas = [
            (RespostaTentativa, RespostaTentativa.tentativa_id.in_(tentativas)),
            (TentativaQuestao, TentativaQuestao.tentativa_id.in_(tentativas)),
            (Tentativa, Tentativa.user_id == user_id),
            (Mensagem, Mensagem.conversa_id.in_(conversas)),
            (ResumoEstudo, ResumoEstudo.user_id == user_id),
            (Conversa, Conversa.user_id == user_id),
            (XpEvento, XpEvento.user_id == user_id),
            (ProgressoUsuario, ProgressoUsuario.user_id == user_id),
            (LicaoIniciada, LicaoIniciada.user_id == user_id),
            (StreakUsuario, StreakUsuario.user_id == user_id),
            (ResumoAluno, ResumoAluno.user_id == user_id),
            (ResumoAbertura, ResumoAbertura.user_id == user_id),
            (IaConsumo, IaConsumo.user_id == user_id),
            (TrilhaEstudando, TrilhaEstudando.user_id == user_id),
            (VotoMateria, VotoMateria.user_id == user_id),
            (PerfilUsuario, PerfilUsuario.user_id == user_id),
        ]
        # The ADK session of each conversation (its history lives there too) goes
        # before the conversations, whose ids key it.
        apagados = self._apagar_sessoes_do_agente(user_id)
        for modelo, condicao in etapas:
            n = self.db.execute(delete(modelo).where(condicao)).rowcount
            if n:
                apagados[modelo.__tablename__] = n
        return apagados

    def _apagar_sessoes_do_agente(self, user_id: str) -> dict[str, int]:
        """Best effort and isolated in a savepoint: those tables belong to the
        ADK, so if they are not there (or look different) the rest still goes."""
        ids = [
            str(i)
            for i in self.db.execute(
                select(Conversa.id).where(Conversa.user_id == user_id)
            ).scalars()
        ]
        if not ids:
            return {}
        try:
            with self.db.begin_nested():
                eventos = self.db.execute(
                    text("delete from events where app_name = :app and session_id = any(:ids)"),
                    {"app": ADK_APP_NAME, "ids": ids},
                ).rowcount
                sessoes = self.db.execute(
                    text("delete from sessions where app_name = :app and id = any(:ids)"),
                    {"app": ADK_APP_NAME, "ids": ids},
                ).rowcount
        except DBAPIError:
            logger.warning(
                "não foi possível apagar as sessões do agente de %s", user_id, exc_info=True
            )
            return {}
        return {k: v for k, v in (("events", eventos), ("sessions", sessoes)) if v}

    def materias_proprias(self, user_id: str) -> int:
        """Trilhas the user created. They are kept: other students may be studying
        them."""
        stmt = select(func.count()).select_from(Materia).where(Materia.owner_user_id == user_id)
        return int(self.db.execute(stmt).scalar_one())


def get_usuario_dados_repository(db: DbSession) -> UsuarioDadosRepository:
    return UsuarioDadosRepository(db)


UsuarioDadosRepo = Annotated[UsuarioDadosRepository, Depends(get_usuario_dados_repository)]
