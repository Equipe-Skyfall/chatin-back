"""Tool-calling chat for regular students (`agent_tools_aluno.py`): search
the public curriculum, see own performance, create own trilha. A much
smaller, non-destructive tool set than the admin agent's, but the same
loop/session mechanics under the hood (`AIProvider.conversar_com_agente_
aluno`) - see `app/ai/base.py`.
"""

import logging
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.ai.base import AIProvider
from app.ai.disponibilidade import status_ia
from app.ai.prompts import LICAO_MARCADOR, prompt_licao_modulo
from app.ai.schemas import FerramentaContexto, MensagemAgente, MensagemHistorico
from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
from app.core.falha_ia import TipoFalhaIA
from app.db.session import nova_sessao
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Conversa, Mensagem
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.licao_repository import LicaoRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.resumo_aluno_repository import ResumoAlunoRepository

logger = logging.getLogger(__name__)

_FALHAS_QUE_INDICAM_IA_FORA = {TipoFalhaIA.LIMITE, TipoFalhaIA.INDISPONIVEL, TipoFalhaIA.TIMEOUT}

# Most messages sent to the model in one summary refresh - bounds the prompt when
# a conversation grew a lot (or earlier refreshes kept failing) before this one.
_MAX_MENSAGENS_POR_ATUALIZACAO = 40


def _mensagem_para_historico(mensagem: Mensagem) -> MensagemAgente:
    papel = PAPEL_ASSISTENTE if mensagem.papel == PAPEL_ASSISTENTE else PAPEL_USUARIO
    return MensagemAgente(papel=papel, conteudo=mensagem.conteudo)


def enviar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
    ctx: FerramentaContexto,
    janela: int,
    resposta_pronta: str | None = None,
    *,
    resumo_repo: ResumoAlunoRepository | None = None,
    janela_com_resumo: int | None = None,
    resumo_a_cada: int | None = None,
) -> str:
    """`resposta_pronta` is the answer to a message the app already answered
    itself (a chat shortcut, see `atalho_service`): the agent is not called, the
    turn is stored and recorded in the provider's own history
    (`registrar_troca`), so it shows in the history and the agent remembers it.

    `janela` caps how many of the conversation's most recent messages are
    sent to the model (older ones stay in Postgres, just not in the prompt) -
    bounds prompt size and cost on long chats. `ctx` is this student's
    `FerramentaContexto` (see `routers/chat_aluno.py` for how it's built) -
    `ctx.conversa_id` must equal `conversa.id`.

    With `resumo_repo`, the student's running summary (`ResumoAluno`, across
    all their conversations) goes to the agent as context, and since it carries
    the older context only the last `janela_com_resumo` messages go along with
    it. After the reply the summary is refreshed in the background once the
    conversation has `resumo_a_cada` messages it doesn't cover yet. Without
    `resumo_repo` (or while the summary doesn't exist yet) behaviour is the
    plain `janela`."""

    def _salvar(papel: str, conteudo: str, **extras) -> Mensagem:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        mensagem = conversa_repo.add_mensagem(
            Mensagem(conversa_id=conversa.id, papel=papel, conteudo=conteudo, ordem=ordem, **extras)
        )
        conversa_repo.commit()
        return mensagem

    try:
        pergunta = _salvar(PAPEL_USUARIO, texto_usuario)
    except IntegrityError as exc:
        # Two simultaneous turns on the same conversa both computed the same
        # `ordem` - the unique (conversa_id, ordem) constraint let only one
        # through. This is the only concurrency guard on the student chat.
        conversa_repo.rollback()
        raise ConversaOcupadaException() from exc

    if resposta_pronta is not None:
        _salvar(PAPEL_ASSISTENTE, resposta_pronta)
        conversa_repo.tocar(conversa.id)
        conversa_repo.commit()
        ai_provider.registrar_troca(conversa.id, texto_usuario, resposta_pronta)
        return resposta_pronta

    resumo = resumo_repo.get_by_user(conversa.user_id) if resumo_repo is not None else None
    if resumo is not None and janela_com_resumo is not None:
        janela = janela_com_resumo

    recarregada = conversa_repo.get_with_mensagens(conversa.id)
    historico = [_mensagem_para_historico(m) for m in recarregada.mensagens[-janela:]]

    conteudo_modulo = None
    if conversa.modulo_id is not None:
        modulo = modulo_repo.get(conversa.modulo_id)
        if modulo is not None:
            conteudo_modulo = modulo.conteudo

    resposta = ai_provider.conversar_com_agente_aluno(
        historico, conteudo_modulo, ctx, resumo.resumo if resumo is not None else None
    )
    # The sources the agent's `buscar_fontes_web` tool collected this turn
    # (US-10) - stored with the reply, tied to the question that prompted them.
    fontes = [asdict(f) for f in ctx.fontes_web] or None
    _salvar(
        PAPEL_ASSISTENTE,
        resposta,
        fontes=fontes,
        pergunta_id=pergunta.id if fontes else None,
    )
    conversa_repo.tocar(conversa.id)
    conversa_repo.commit()

    if resumo_repo is not None and resumo_a_cada is not None:
        ja_resumidas = resumo.mensagens_resumidas.get(str(conversa.id), 0) if resumo else 0
        # `recarregada` has the question; the reply was stored just above.
        if len(recarregada.mensagens) + 1 - ja_resumidas >= resumo_a_cada:
            if ctx.background_tasks is not None:
                ctx.background_tasks.add_task(
                    atualizar_resumo_aluno_em_background,
                    conversa.user_id,
                    conversa.id,
                    ai_provider,
                    resumo_a_cada,
                )
            else:
                # No BackgroundTasks handed in (ctx built outside a real HTTP
                # request, e.g. a test) - do it inline rather than drop it.
                atualizar_resumo_aluno(
                    conversa.user_id,
                    conversa.id,
                    conversa_repo,
                    resumo_repo,
                    ai_provider,
                    resumo_a_cada,
                )
    return resposta


def atualizar_resumo_aluno(
    user_id: str,
    conversa_id: uuid.UUID,
    conversa_repo: ConversaRepository,
    resumo_repo: ResumoAlunoRepository,
    ai_provider: AIProvider,
    resumo_a_cada: int,
) -> bool:
    """Folds the messages of `conversa_id` that the student's summary doesn't
    cover yet into it - only once there are `resumo_a_cada` of them - and
    stores the result. Returns whether the summary was updated. A provider
    failure keeps the previous summary (RNF6): the progress isn't advanced, so
    the next turn retries with the same messages plus the new ones."""
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != user_id:
        return False

    resumo = resumo_repo.get_by_user(user_id)
    progresso = dict(resumo.mensagens_resumidas) if resumo is not None else {}
    novas = conversa.mensagens[progresso.get(str(conversa_id), 0) :]
    if len(novas) < resumo_a_cada:
        return False

    try:
        texto = ai_provider.resumir_historico_aluno(
            resumo.resumo if resumo is not None else None,
            [_mensagem_para_historico(m) for m in novas[-_MAX_MENSAGENS_POR_ATUALIZACAO:]],
        )
    except ProvedorIAIndisponivelException:
        logger.warning(
            "Falha ao atualizar o resumo do aluno %s; mantendo o anterior.", user_id, exc_info=True
        )
        return False

    progresso[str(conversa_id)] = len(conversa.mensagens)
    resumo_repo.salvar(user_id, texto, progresso)
    resumo_repo.commit()
    return True


def atualizar_resumo_aluno_em_background(
    user_id: str, conversa_id: uuid.UUID, ai_provider: AIProvider, resumo_a_cada: int
) -> None:
    """Background task body: runs after the chat reply went out, on its own
    session (the request's is closed by then - see `nova_sessao`). Nothing to
    propagate to, so any failure is only logged."""
    db = nova_sessao()
    try:
        atualizar_resumo_aluno(
            user_id,
            conversa_id,
            ConversaRepository(db),
            ResumoAlunoRepository(db),
            ai_provider,
            resumo_a_cada,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Falha inesperada ao atualizar o resumo do aluno %s", user_id)
    finally:
        db.close()


def enviar_licao(
    conversa: Conversa,
    user_id: str,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    licao_repo: LicaoRepository,
    ai_provider: AIProvider,
    ctx: FerramentaContexto,
) -> str | None:
    """Opens the módulo with the agent explaining it in full (only asking at
    the end whether the student has doubts) and flips `start_lesson` on, which
    unlocks the módulo's quiz. Returns the lesson text, or `None` when this
    student already had it (nothing is sent to the model again).

    The student never typed the triggering turn, so only the assistant's reply
    is stored in `mensagens`. If the model fails the flag stays off and the
    next time the module is opened the lesson is tried again."""
    modulo = modulo_repo.get(conversa.modulo_id) if conversa.modulo_id is not None else None
    if modulo is None or licao_repo.existe(user_id, modulo.id):
        return None

    pedido = MensagemAgente(papel=PAPEL_USUARIO, conteudo=prompt_licao_modulo(modulo.titulo))
    try:
        resposta = ai_provider.conversar_com_agente_aluno([pedido], modulo.conteudo, ctx)
    except ProvedorIAIndisponivelException as exc:
        # The student is told the AI is down and the quiz stops asking for the
        # lesson (see `status_ia`); the flag stays off so a later open retries.
        if exc.tipo in _FALHAS_QUE_INDICAM_IA_FORA:
            status_ia.marcar_indisponivel()
        raise
    status_ia.registrar_sucesso()

    ordem = conversa_repo.proxima_ordem(conversa.id)
    try:
        conversa_repo.add_mensagem(
            Mensagem(
                conversa_id=conversa.id, papel=PAPEL_ASSISTENTE, conteudo=resposta, ordem=ordem
            )
        )
        licao_repo.marcar(user_id, modulo.id)
        conversa_repo.tocar(conversa.id)
        conversa_repo.commit()
    except IntegrityError as exc:
        conversa_repo.rollback()
        raise ConversaOcupadaException() from exc
    return resposta


def anexar_fontes_ao_historico(
    historico: list[MensagemHistorico], mensagens: list[Mensagem]
) -> list[MensagemHistorico]:
    """The ADK session (where `AI_PROVIDER=adk` reads history from) knows
    nothing about the sources shown under a reply - they live on the
    `mensagens` rows. Re-attaches them by matching the assistant text, which
    is the same string in both places."""
    por_conteudo = {m.conteudo: m for m in mensagens if m.papel == PAPEL_ASSISTENTE and m.fontes}
    resultado = []
    for item in historico:
        if item.papel == PAPEL_USUARIO and (item.conteudo or "").startswith(LICAO_MARCADOR):
            continue  # the lesson's trigger turn - the student never wrote it
        origem = por_conteudo.get(item.conteudo) if item.papel == PAPEL_ASSISTENTE else None
        if origem is not None:
            item = replace(item, fontes=origem.fontes, pergunta_id=origem.pergunta_id)
        resultado.append(item)
    return resultado


def obter_ou_gerar_resumo(
    conversa: Conversa, conversa_repo: ConversaRepository, ai_provider: AIProvider
) -> str | None:
    """Lazily (re)generates the conversation's summary - only when it's
    missing or stale (the conversation moved on since the last summary), not
    on every read and never on every message. Returns None for a conversation
    with no messages yet (nothing to summarize) or when the AI provider fails
    (RNF6) - one conversation's summary failing must not break the rest of
    the list (see `listar_resumos`), and the stale summary just gets retried
    on the next call instead of being persisted as a failure."""
    esta_atualizado = (
        conversa.resumo is not None
        and conversa.resumo_gerado_em is not None
        and conversa.resumo_gerado_em >= conversa.updated_at
    )
    if esta_atualizado:
        return conversa.resumo

    completa = conversa_repo.get_with_mensagens(conversa.id)
    if not completa.mensagens:
        return None

    historico = [_mensagem_para_historico(m) for m in completa.mensagens]
    try:
        resumo = ai_provider.resumir_conversa(historico)
    except ProvedorIAIndisponivelException:
        logger.warning(
            "Falha ao gerar resumo da conversa %s; mantendo resumo anterior (se houver).",
            conversa.id,
            exc_info=True,
        )
        return conversa.resumo
    completa.resumo = resumo
    completa.resumo_gerado_em = datetime.now(UTC)
    conversa_repo.add(completa)
    conversa_repo.commit()
    return resumo
