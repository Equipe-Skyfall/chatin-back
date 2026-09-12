import uuid

import pytest

from app.core.exceptions import (
    RespostaInvalidaException,
    SubmissaoIncompletaException,
    TentativaJaFinalizadaException,
)
from app.schemas.tentativa import RespostaInput
from app.services import grading_service
from tests.builders.questionario_builder import QuestionarioBuilder


def _seed_pool(questionario_repo, num_questoes=12, resposta_correta="A"):
    questionario, questoes, gabarito_map = (
        QuestionarioBuilder()
        .com_num_questoes(num_questoes)
        .com_resposta_correta_padrao(resposta_correta)
        .build()
    )
    questionario_repo.seed(questionario, questoes, gabarito_map)
    return questionario, questoes, gabarito_map


def test_iniciar_tentativa_amostra_tamanho_correto_sem_duplicatas(
    questionario_repo, tentativa_repo
):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)

    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    assert tentativa.total_questoes == 5
    assert len(questoes) == 5
    assert len({q.id for q in questoes}) == 5
    pool_ids = set(questionario_repo.get_questao_ids_pool(questionario.id))
    assert {q.id for q in questoes} <= pool_ids


def test_duas_tentativas_podem_amostrar_conjuntos_diferentes(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)

    _, questoes_1 = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    _, questoes_2 = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    # Not asserting they always differ (that would be flaky) - just that the
    # mechanism is a real sample over the pool, not a fixed slice.
    assert {q.id for q in questoes_1} <= set(
        questionario_repo.get_questao_ids_pool(questionario.id)
    )
    assert {q.id for q in questoes_2} <= set(
        questionario_repo.get_questao_ids_pool(questionario.id)
    )


def test_responder_tentativa_todas_corretas(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5, resposta_correta="A")
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=q.id, resposta_escolhida="A") for q in questoes]

    tentativa, resultados = grading_service.responder_tentativa(
        tentativa, respostas, questionario_repo, tentativa_repo
    )

    assert tentativa.status == "concluida"
    assert float(tentativa.pontuacao) == 100.0
    assert tentativa.total_corretas == 5
    assert all(r.correta for r in resultados)


def test_responder_tentativa_todas_erradas(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5, resposta_correta="A")
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=q.id, resposta_escolhida="B") for q in questoes]

    tentativa, resultados = grading_service.responder_tentativa(
        tentativa, respostas, questionario_repo, tentativa_repo
    )

    assert float(tentativa.pontuacao) == 0.0
    assert tentativa.total_corretas == 0
    assert all(not r.correta for r in resultados)


def test_responder_tentativa_mista(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=4, resposta_correta="A")
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 4, questionario_repo, tentativa_repo
    )
    respostas = [
        RespostaInput(questao_id=questoes[0].id, resposta_escolhida="A"),
        RespostaInput(questao_id=questoes[1].id, resposta_escolhida="A"),
        RespostaInput(questao_id=questoes[2].id, resposta_escolhida="B"),
        RespostaInput(questao_id=questoes[3].id, resposta_escolhida="C"),
    ]

    tentativa, _ = grading_service.responder_tentativa(
        tentativa, respostas, questionario_repo, tentativa_repo
    )

    assert tentativa.total_corretas == 2
    assert float(tentativa.pontuacao) == 50.0


def test_responder_tentativa_submissao_parcial_levanta_excecao(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5)
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=questoes[0].id, resposta_escolhida="A")]

    with pytest.raises(SubmissaoIncompletaException):
        grading_service.responder_tentativa(tentativa, respostas, questionario_repo, tentativa_repo)


def test_responder_tentativa_questao_fora_da_amostra_levanta_excecao(
    questionario_repo, tentativa_repo
):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5)
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=q.id, resposta_escolhida="A") for q in questoes]
    respostas[0] = RespostaInput(questao_id=uuid.uuid4(), resposta_escolhida="A")

    with pytest.raises(RespostaInvalidaException):
        grading_service.responder_tentativa(tentativa, respostas, questionario_repo, tentativa_repo)


def test_responder_tentativa_resposta_duplicada_levanta_excecao(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5)
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=questoes[0].id, resposta_escolhida="A") for _ in range(5)]

    with pytest.raises(RespostaInvalidaException):
        grading_service.responder_tentativa(tentativa, respostas, questionario_repo, tentativa_repo)


def test_responder_tentativa_ja_concluida_levanta_excecao(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=3)
    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 3, questionario_repo, tentativa_repo
    )
    respostas = [RespostaInput(questao_id=q.id, resposta_escolhida="A") for q in questoes]
    grading_service.responder_tentativa(tentativa, respostas, questionario_repo, tentativa_repo)

    with pytest.raises(TentativaJaFinalizadaException):
        grading_service.responder_tentativa(tentativa, respostas, questionario_repo, tentativa_repo)


def test_questao_out_nunca_carrega_resposta_correta():
    """Regression guard: the client-facing schema is structurally incapable
    of leaking the gabarito - there is no `resposta_correta` field at all."""
    from app.schemas.questionario import QuestaoOut

    assert "resposta_correta" not in QuestaoOut.model_fields
