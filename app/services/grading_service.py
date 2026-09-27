"""Attempt sampling + deterministic grading.

`get_gabarito_map` on `QuestionarioRepository` is the only place the gabarito
is ever read - this module is the only caller of it. Sampling questions for an
attempt is a DB-only operation (`random.sample` over already-stored ids) - it
never triggers a new AI call, which is the whole point of generating the pool
once on módulo creation.
"""

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    ConteudoIndisponivelException,
    RespostaInvalidaException,
    SubmissaoIncompletaException,
    TentativaJaFinalizadaException,
)
from app.models.questao import Questao
from app.models.tentativa import (
    STATUS_CONCLUIDA,
    STATUS_EM_ANDAMENTO,
    RespostaTentativa,
    Tentativa,
    TentativaQuestao,
)
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tentativa_repository import TentativaRepository
from app.schemas.tentativa import RespostaInput, RespostaResultadoOut
from app.services import dificuldade_service


def mesmo_escopo(
    tentativa: Tentativa,
    *,
    questionario_id: uuid.UUID | None,
    tema_id: uuid.UUID | None,
    pratica: bool,
) -> bool:
    """Whether an open `tentativa` is the very quiz being asked for: the same
    módulo questionário (or the same tema review) AND the same kind (graded vs
    practice). Anything else is a different quiz, and must never be handed
    back in its place."""
    return (
        tentativa.questionario_id == questionario_id
        and tentativa.tema_id == tema_id
        and tentativa.pratica == pratica
    )


def questionario_aberto_como_lista(
    tentativa: Tentativa, questionario_repo: QuestionarioRepository
) -> tuple[Tentativa, list[Questao]]:
    """Reconstructs the (tentativa, questões) shape `iniciar_tentativa*`
    returns, from an already-open questionário's fixed sample - used to resume
    it instead of sampling a new one (see `iniciar_tentativa_com_pool`). A
    questionário left open by a student who never came back to finish it still
    counts: coming back to the same quiz gives the same questions, so leaving
    and returning can't be used to re-roll a sample."""
    itens = sorted(tentativa.questoes_selecionadas, key=lambda i: i.ordem)
    questoes = questionario_repo.get_questoes_by_ids([i.questao_id for i in itens])
    ordem_map = {i.questao_id: i.ordem for i in itens}
    questoes_ordenadas = sorted(questoes, key=lambda q: ordem_map[q.id])
    return tentativa, questoes_ordenadas


def iniciar_tentativa_com_pool(
    pool_ids: list[uuid.UUID],
    user_id: str,
    num_questoes: int,
    questionario_repo: QuestionarioRepository,
    tentativa_repo: TentativaRepository,
    *,
    questionario_id: uuid.UUID | None,
    tema_id: uuid.UUID | None,
    pratica: bool = False,
) -> tuple[Tentativa, list[Questao]]:
    """Shared by `iniciar_tentativa`, `iniciar_tentativa_tema` and
    `questionario_personalizado_service`. A student has at most 1 open
    (unfinished) questionário at a time: if the open one is the very quiz being
    asked for (same scope and kind - see `mesmo_escopo`) it is resumed with its
    fixed sample; if it is any other quiz it is discarded, and a new sample is
    drawn for the one being asked for. Leaving a quiz half-done therefore never
    hands its questions to a different módulo."""
    questionario_aberto = tentativa_repo.get_questionario_aberto_by_user(user_id)
    if questionario_aberto is not None:
        if mesmo_escopo(
            questionario_aberto, questionario_id=questionario_id, tema_id=tema_id, pratica=pratica
        ):
            return questionario_aberto_como_lista(questionario_aberto, questionario_repo)
        tentativa_repo.descartar(questionario_aberto)

    quantidade = min(num_questoes, len(pool_ids))

    # Adaptive selection: a student doing well overall gets more hard
    # questions from the pool, one struggling gets more easy ones - see
    # `dificuldade_service`. Falls back to an effectively uniform weighting
    # (every question "médio") until enough answer data exists.
    nivel = dificuldade_service.nivel_do_aluno(tentativa_repo.media_pontuacao_concluidas(user_id))
    dificuldades = dificuldade_service.dificuldade_por_questao(pool_ids, questionario_repo)
    pesos = {qid: dificuldade_service.PESOS_POR_NIVEL[nivel][dificuldades[qid]] for qid in pool_ids}
    selecionados = dificuldade_service.amostra_ponderada_sem_reposicao(pool_ids, pesos, quantidade)

    tentativa = Tentativa(
        questionario_id=questionario_id,
        tema_id=tema_id,
        user_id=user_id,
        status=STATUS_EM_ANDAMENTO,
        total_questoes=quantidade,
        pratica=pratica,
    )
    tentativa_repo.add(tentativa)
    try:
        # Also where a concurrent request for the same user would collide -
        # see the partial unique index on `tentativas(user_id) WHERE
        # status='em_andamento'`, added specifically so this SELECT-then-
        # INSERT (the open-tentativa check above, then this insert) can't
        # race two open tentativas into existence.
        tentativa_repo.flush()
    except IntegrityError:
        tentativa_repo.db.rollback()
        questionario_aberto = tentativa_repo.get_questionario_aberto_by_user(user_id)
        if questionario_aberto is None or not mesmo_escopo(
            questionario_aberto, questionario_id=questionario_id, tema_id=tema_id, pratica=pratica
        ):
            raise  # not a concurrent start of this same quiz - re-raise as-is
        return questionario_aberto_como_lista(questionario_aberto, questionario_repo)

    itens = [
        TentativaQuestao(tentativa_id=tentativa.id, questao_id=qid, ordem=idx)
        for idx, qid in enumerate(selecionados)
    ]
    tentativa_repo.add_tentativa_questoes(itens)
    tentativa_repo.commit()
    tentativa_repo.refresh(tentativa)

    questoes = questionario_repo.get_questoes_by_ids(selecionados)
    ordem_map = {qid: idx for idx, qid in enumerate(selecionados)}
    questoes_ordenadas = sorted(questoes, key=lambda q: ordem_map[q.id])
    return tentativa, questoes_ordenadas


def iniciar_tentativa(
    questionario_id: uuid.UUID,
    user_id: str,
    num_questoes: int,
    questionario_repo: QuestionarioRepository,
    tentativa_repo: TentativaRepository,
) -> tuple[Tentativa, list[Questao]]:
    pool_ids = questionario_repo.get_questao_ids_pool_graduavel(questionario_id)
    return iniciar_tentativa_com_pool(
        pool_ids,
        user_id,
        num_questoes,
        questionario_repo,
        tentativa_repo,
        questionario_id=questionario_id,
        tema_id=None,
    )


def iniciar_tentativa_tema(
    tema_id: uuid.UUID,
    user_id: str,
    num_questoes: int,
    questionario_repo: QuestionarioRepository,
    tentativa_repo: TentativaRepository,
) -> tuple[Tentativa, list[Questao]]:
    """A review quiz mixing questions from every ready módulo's pool under
    the tema - practice only (see `Tentativa`'s docstring for why it doesn't
    touch progress/XP)."""
    pool_ids = questionario_repo.get_questao_ids_pool_por_tema(tema_id)
    if not pool_ids:
        raise ConteudoIndisponivelException(
            "Este tema ainda não tem nenhum módulo com questionário pronto."
        )
    return iniciar_tentativa_com_pool(
        pool_ids,
        user_id,
        num_questoes,
        questionario_repo,
        tentativa_repo,
        questionario_id=None,
        tema_id=tema_id,
        pratica=True,
    )


def responder_tentativa(
    tentativa: Tentativa,
    respostas: list[RespostaInput],
    questionario_repo: QuestionarioRepository,
    tentativa_repo: TentativaRepository,
) -> tuple[Tentativa, list[RespostaResultadoOut]]:
    if tentativa.status == STATUS_CONCLUIDA:
        raise TentativaJaFinalizadaException()

    ids_validos = tentativa_repo.get_tentativa_questao_ids(tentativa.id)
    ids_respondidos = [r.questao_id for r in respostas]

    if len(set(ids_respondidos)) != len(ids_respondidos):
        raise RespostaInvalidaException("Respostas duplicadas para a mesma questão.")
    if any(qid not in ids_validos for qid in ids_respondidos):
        raise RespostaInvalidaException("Uma ou mais questões não pertencem a esta tentativa.")
    if len(ids_respondidos) != len(ids_validos):
        raise SubmissaoIncompletaException()

    gabarito_map = questionario_repo.get_gabarito_map(list(ids_validos))
    questoes = questionario_repo.get_questoes_by_ids(list(ids_validos))
    explicacao_map = {q.id: q.explicacao for q in questoes}
    enunciado_map = {q.id: q.enunciado for q in questoes}

    resultados: list[RespostaResultadoOut] = []
    respostas_model: list[RespostaTentativa] = []
    total_corretas = 0

    for resposta in respostas:
        resposta_correta = gabarito_map[resposta.questao_id]
        correta = resposta.resposta_escolhida == resposta_correta
        total_corretas += int(correta)
        resultados.append(
            RespostaResultadoOut(
                questao_id=resposta.questao_id,
                enunciado=enunciado_map[resposta.questao_id],
                resposta_escolhida=resposta.resposta_escolhida,
                resposta_correta=resposta_correta,
                correta=correta,
                explicacao=explicacao_map.get(resposta.questao_id),
            )
        )
        respostas_model.append(
            RespostaTentativa(
                tentativa_id=tentativa.id,
                questao_id=resposta.questao_id,
                resposta_escolhida=resposta.resposta_escolhida,
                correta=correta,
            )
        )

    tentativa_repo.add_respostas(respostas_model)
    pontuacao = round((total_corretas / len(respostas)) * 100, 2)
    tentativa_repo.marcar_concluida(tentativa, pontuacao, total_corretas)
    tentativa_repo.commit()
    tentativa_repo.refresh(tentativa)

    return tentativa, resultados
