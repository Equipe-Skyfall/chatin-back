"""Background completion of tema/módulo creation, so `POST /materias/{id}/
temas` and `POST /temas/{id}/modulos/gerar-automaticamente` can respond
immediately (the Tema is inserted with status `'gerando'` synchronously,
which costs no AI call) instead of blocking the request for the ~1-2+
minutes those AI calls actually take (see TODO.md's "Regeneração em lote
trava a requisição HTTP por minutos").

Runs via FastAPI's `BackgroundTasks`, *after* the response is already sent -
by then the request's own DB session is closed, so every function here opens
its own fresh session (`app.db.session.nova_sessao`) and closes it when done,
never touching the request-scoped repos it was handed at call time.

No new queue/worker/broker: this is in-process, same instance, same as any
other request. The real risk is the instance restarting mid-task (Render's
free tier can do this) - a tema stuck on `'gerando'` forever. `Tema.status`
already models exactly this: `reabrir_temas_travados` sweeps anything stuck
past a timeout back to `'erro'` so the client's poll (see `GET /temas/{id}`)
eventually gets a terminal state instead of spinning forever; it's called
opportunistically on read, not via a cron (no scheduler infrastructure
exists in this app, and one sweep-on-read is enough at this app's scale).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.ai.base import AIProvider
from app.core.exceptions import AppException
from app.db.session import nova_sessao
from app.models.tema import STATUS_ERRO, STATUS_GERANDO
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tema_repository import TemaRepository
from app.services import curriculo_service
from app.services.fonte_pipeline import buscar_fontes_tema

logger = logging.getLogger(__name__)

# A stuck-on-"gerando" tema older than this is almost certainly a dead
# background task (instance restart mid-run), not one still legitimately
# in progress - the real thing takes well under this even in the worst case
# observed so far (TODO.md: "2m38s ao vivo").
TIMEOUT_GERACAO = timedelta(minutes=10)


def completar_criacao_tema(tema_id: uuid.UUID, ai_provider: AIProvider) -> None:
    """Background task body for `POST /materias/{id}/temas`: runs
    `buscar_fontes_tema` (the AI call `criar_tema_pendente` deferred) against
    a fresh session. `buscar_fontes_tema` already sets the tema's status to
    `'pronto'`/`'erro'` and commits either way - this wrapper only exists to
    own the session's lifecycle and make sure nothing here ever raises into
    `BackgroundTasks`' runner unhandled."""
    db = nova_sessao()
    try:
        tema_repo = TemaRepository(db)
        tema = tema_repo.get(tema_id)
        if tema is None:
            logger.warning("completar_criacao_tema: tema %s não existe mais", tema_id)
            return
        buscar_fontes_tema(tema, tema_repo, ai_provider)
    except AppException as exc:
        # Already recorded as status='erro' by buscar_fontes_tema itself -
        # just log, there's no request/caller left to return this to.
        logger.warning("Falha ao completar criação do tema %s: %s", tema_id, exc.detail)
    except Exception:  # noqa: BLE001 - background task, nothing to propagate to
        logger.exception("Falha inesperada ao completar criação do tema %s", tema_id)
    finally:
        db.close()


def completar_divisao_em_modulos(
    tema_id: uuid.UUID, pool_size: int, ai_provider: AIProvider
) -> None:
    """Background task body for `POST /temas/{id}/modulos/gerar-
    automaticamente`: runs `curriculo_service.dividir_tema_em_modulos`
    (already resilient per-módulo - one failing módulo doesn't stop the
    rest) against a fresh session."""
    db = nova_sessao()
    try:
        tema_repo = TemaRepository(db)
        modulo_repo = ModuloRepository(db)
        questionario_repo = QuestionarioRepository(db)
        curriculo_service.dividir_tema_em_modulos(
            tema_id, pool_size, tema_repo, modulo_repo, questionario_repo, ai_provider
        )
    except AppException as exc:
        logger.warning("Falha ao dividir tema %s em módulos: %s", tema_id, exc.detail)
    except Exception:  # noqa: BLE001
        logger.exception("Falha inesperada ao dividir tema %s em módulos", tema_id)
    finally:
        db.close()


def reabrir_temas_travados(tema_repo: TemaRepository) -> None:
    """Opportunistic sweep, called on read (see `GET /temas/{id}`,
    `GET /materias`): flips any tema stuck on `'gerando'` past
    `TIMEOUT_GERACAO` to `'erro'`, so a client polling status eventually
    reaches a terminal state instead of waiting forever on a background task
    that silently died (e.g. the instance restarted mid-run)."""
    limite = datetime.now(UTC) - TIMEOUT_GERACAO
    for tema in tema_repo.list_travados_desde(STATUS_GERANDO, limite):
        tema_repo.atualizar_status(tema, STATUS_ERRO)
    tema_repo.commit()
