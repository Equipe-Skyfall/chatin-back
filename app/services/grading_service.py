"""Attempt sampling + deterministic grading.

`get_gabarito_map` on `QuestionarioRepository` is the only place the gabarito
is ever read - this module is the only caller of it. Sampling questions for an
attempt is a DB-only operation (`random.sample` over already-stored ids) - it
never triggers a new AI call, which is the whole point of generating the pool
once on módulo creation.
"""

import random
import uuid

from app.core.exceptions import (
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


def iniciar_tentativa(
    questionario_id: uuid.UUID,
    user_id: str,
    num_questoes: int,
    questionario_repo: QuestionarioRepository,
    tentativa_repo: TentativaRepository,
) -> tuple[Tentativa, list[Questao]]:
    pool_ids = questionario_repo.get_questao_ids_pool(questionario_id)
    quantidade = min(num_questoes, len(pool_ids))
    selecionados = random.sample(pool_ids, quantidade)

    tentativa = Tentativa(
        questionario_id=questionario_id,
        user_id=user_id,
        status=STATUS_EM_ANDAMENTO,
        total_questoes=quantidade,
    )
    tentativa_repo.add(tentativa)
    tentativa_repo.flush()

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
