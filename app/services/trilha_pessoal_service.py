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
free tier can do this) - a tema (or módulo) stuck on `'gerando'` forever.
`reabrir_temas_travados`/`reabrir_modulos_travados` sweep anything stuck
past a timeout back to `'erro'` so a client's poll eventually gets a
terminal state instead of spinning forever; called opportunistically on
read, not via a cron (no scheduler infrastructure exists in this app, and
one sweep-on-read is enough at this app's scale).

`completar_criacao_trilha_pessoal` is the one-shot path used by the student
agent's `criar_minha_trilha` - it chains source research straight into the
módulo auto-split so a student ends up with an actually studyable trilha
from a single action, not just an empty tema. `GET /temas/{id}/status`
(`calcular_status_tema`) is the single "is it actually done" signal for
that path - `Tema.status == 'pronto'` alone only ever meant "sources found,
ready to receive módulos", never "fully generated".
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.ai.base import AIProvider
from app.core.exceptions import AppException
from app.db.session import nova_sessao
from app.models.modulo import STATUS_ERRO as MODULO_STATUS_ERRO
from app.models.modulo import STATUS_GERANDO as MODULO_STATUS_GERANDO
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.tema import STATUS_ERRO, STATUS_GERANDO
from app.models.tema import STATUS_PRONTO as TEMA_STATUS_PRONTO
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


def completar_criacao_trilha_pessoal(
    tema_id: uuid.UUID, pool_size: int, ai_provider: AIProvider
) -> None:
    """Background task body for the student agent's `criar_minha_trilha`
    (`app/services/agent_tools_aluno.py`) - chains source research
    (`buscar_fontes_tema`) straight into the módulo auto-split
    (`curriculo_service.dividir_tema_em_modulos`) in one background
    execution, so "create my own trilha" ends up with actual studyable
    content instead of just an empty tema.

    Deliberately a separate function from `completar_criacao_tema` (used by
    `POST /materias/{id}/temas` for both admin and student manual creation)
    rather than that function auto-chaining into a split: an admin (or a
    student) using that endpoint directly may want to add módulos by hand
    afterward, not have them auto-generated - this one-shot path is only
    for the chat tool, which promises the student a fully generated trilha
    from a single action.

    If source research itself fails, `buscar_fontes_tema` already marks the
    tema `'erro'` - nothing further happens. If sources succeed but the
    split fails entirely (e.g. `planejar_modulos` itself errors, before any
    módulo exists), the tema is *also* marked `'erro'` here - unlike
    `completar_divisao_em_modulos`, which leaves the tema `'pronto'` even on
    a totally failed split, since that endpoint's tema might already have
    had módulos or a legitimate "add them later" intent behind it. A
    partial split (some módulos created, some failed) is left as `'pronto'`
    either way - `curriculo_service.dividir_tema_em_modulos` already
    tolerates per-módulo failure, and a partially-generated trilha is still
    a trilha, not a total failure - see `GET /temas/{id}/status` for how a
    caller tells a full vs. partial vs. failed split apart."""
    db = nova_sessao()
    try:
        tema_repo = TemaRepository(db)
        tema = tema_repo.get(tema_id)
        if tema is None:
            logger.warning("completar_criacao_trilha_pessoal: tema %s não existe mais", tema_id)
            return

        buscar_fontes_tema(tema, tema_repo, ai_provider)
        tema_repo.refresh(tema)
        if tema.status != TEMA_STATUS_PRONTO:
            return  # already marked 'erro' by buscar_fontes_tema - stop here

        modulo_repo = ModuloRepository(db)
        questionario_repo = QuestionarioRepository(db)
        try:
            criados = curriculo_service.dividir_tema_em_modulos(
                tema_id, pool_size, tema_repo, modulo_repo, questionario_repo, ai_provider
            )
        except AppException as exc:
            logger.warning(
                "Divisão em módulos falhou totalmente pro tema %s: %s", tema_id, exc.detail
            )
            tema_repo.atualizar_status(tema, STATUS_ERRO)
            tema_repo.commit()
            return
        if not criados:
            logger.warning(
                "Divisão em módulos não criou nenhum módulo pro tema %s (plano vazio)", tema_id
            )
            tema_repo.atualizar_status(tema, STATUS_ERRO)
            tema_repo.commit()
    except Exception:  # noqa: BLE001 - background task, nothing to propagate to
        logger.exception("Falha inesperada ao criar trilha pessoal (tema %s)", tema_id)
    finally:
        db.close()


def reabrir_modulos_travados(modulo_repo: ModuloRepository) -> None:
    """Same purpose as `reabrir_temas_travados`, for módulos - a módulo
    stuck on `'gerando'` past `TIMEOUT_GERACAO` means the background task
    generating it (`completar_divisao_em_modulos`/
    `completar_criacao_trilha_pessoal`) died mid-run."""
    limite = datetime.now(UTC) - TIMEOUT_GERACAO
    for modulo in modulo_repo.list_travados_desde(MODULO_STATUS_GERANDO, limite):
        modulo_repo.atualizar_status(modulo, MODULO_STATUS_ERRO)
    modulo_repo.commit()


def calcular_status_tema(tema, modulos: list) -> dict:
    """Pure aggregation, no I/O - the single "is this trilha actually ready
    to study" signal `GET /temas/{id}/status` exposes, computed fresh from
    `tema.status` + every módulo's own status rather than stored anywhere.
    Kept out of the router so it's unit-testable without a DB.

    `tema.status == 'pronto'` alone only ever meant "sources found, ready
    to *receive* módulos" (see `criar_modulo`'s check) - it was never a
    "fully generated" signal, and redefining it would break that existing
    use. `pronto_para_estudar` is the actual "nothing left in flight, at
    least one módulo exists" answer a poller wants."""
    total = len(modulos)
    prontos = sum(1 for m in modulos if m.status == MODULO_STATUS_PRONTO)
    com_erro = sum(1 for m in modulos if m.status == MODULO_STATUS_ERRO)
    gerando = sum(1 for m in modulos if m.status == MODULO_STATUS_GERANDO)
    return {
        "tema_status": tema.status,
        "modulos_total": total,
        "modulos_prontos": prontos,
        "modulos_com_erro": com_erro,
        "modulos_gerando": gerando,
        "pronto_para_estudar": tema.status == TEMA_STATUS_PRONTO and total > 0 and gerando == 0,
    }


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
