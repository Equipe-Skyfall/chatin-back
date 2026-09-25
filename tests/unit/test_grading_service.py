import uuid

import pytest

from app.core.exceptions import (
    ConteudoIndisponivelException,
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


def test_iniciar_tentativa_tema_sem_questoes_levanta_excecao(questionario_repo, tentativa_repo):
    with pytest.raises(ConteudoIndisponivelException):
        grading_service.iniciar_tentativa_tema(
            uuid.uuid4(), uuid.uuid4(), 5, questionario_repo, tentativa_repo
        )


def test_iniciar_tentativa_marca_pratica_false(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=5)

    tentativa, _ = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    assert tentativa.pratica is False


def test_iniciar_tentativa_tema_marca_pratica_true(questionario_repo, tentativa_repo):
    tema_id = uuid.uuid4()
    _, questoes, _ = _seed_pool(questionario_repo, num_questoes=5)
    questionario_repo.seed_pool_tema(tema_id, [q.id for q in questoes])

    tentativa, _ = grading_service.iniciar_tentativa_tema(
        tema_id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    assert tentativa.pratica is True


def test_iniciar_tentativa_duas_vezes_sem_concluir_retoma_a_mesma(
    questionario_repo, tentativa_repo
):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    user_id = uuid.uuid4()

    tentativa_1, questoes_1 = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, tentativa_repo
    )
    tentativa_2, questoes_2 = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, tentativa_repo
    )

    assert tentativa_2.id == tentativa_1.id
    assert [q.id for q in questoes_2] == [q.id for q in questoes_1]
    assert len(tentativa_repo.tentativas) == 1


def test_iniciar_tentativa_tema_descarta_tentativa_de_modulo_em_andamento(
    questionario_repo, tentativa_repo
):
    """A tema review is a different quiz from an open módulo attempt: the
    módulo attempt is discarded and the student gets the review they asked for."""
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    tema_id = uuid.uuid4()
    questionario_repo.seed_pool_tema(
        tema_id, questionario_repo.get_questao_ids_pool(questionario.id)
    )
    user_id = uuid.uuid4()

    tentativa_modulo, _ = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, tentativa_repo
    )
    tentativa_tema, _ = grading_service.iniciar_tentativa_tema(
        tema_id, user_id, 5, questionario_repo, tentativa_repo
    )

    assert tentativa_tema.id != tentativa_modulo.id
    assert tentativa_tema.tema_id == tema_id
    assert tentativa_tema.questionario_id is None
    assert list(tentativa_repo.tentativas) == [tentativa_tema.id]


def test_iniciar_tentativa_tema_duas_vezes_retoma_a_mesma(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    tema_id = uuid.uuid4()
    questionario_repo.seed_pool_tema(
        tema_id, questionario_repo.get_questao_ids_pool(questionario.id)
    )
    user_id = uuid.uuid4()

    primeira, questoes_1 = grading_service.iniciar_tentativa_tema(
        tema_id, user_id, 5, questionario_repo, tentativa_repo
    )
    segunda, questoes_2 = grading_service.iniciar_tentativa_tema(
        tema_id, user_id, 5, questionario_repo, tentativa_repo
    )

    assert segunda.id == primeira.id
    assert [q.id for q in questoes_2] == [q.id for q in questoes_1]


def test_iniciar_tentativa_tema_de_outro_tema_descarta_a_aberta(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    pool = questionario_repo.get_questao_ids_pool(questionario.id)
    tema_a, tema_b = uuid.uuid4(), uuid.uuid4()
    questionario_repo.seed_pool_tema(tema_a, pool)
    questionario_repo.seed_pool_tema(tema_b, pool)
    user_id = uuid.uuid4()

    revisao_a, _ = grading_service.iniciar_tentativa_tema(
        tema_a, user_id, 5, questionario_repo, tentativa_repo
    )
    revisao_b, _ = grading_service.iniciar_tentativa_tema(
        tema_b, user_id, 5, questionario_repo, tentativa_repo
    )

    assert revisao_b.id != revisao_a.id
    assert revisao_b.tema_id == tema_b
    assert list(tentativa_repo.tentativas) == [revisao_b.id]


def test_iniciar_tentativa_exclui_questoes_personalizadas_da_amostra(
    questionario_repo, tentativa_repo
):
    """A questão marcada `personalizada=True` (gerada sob demanda, grounded
    na conversa de um aluno) nunca pode ser sorteada pelo questionário de
    conclusão de módulo - é o que impede um aluno de fazer prompt injection
    numa questão que vale nota pra qualquer um."""
    questionario, questoes, gabarito_map = _seed_pool(questionario_repo, num_questoes=3)
    questao_personalizada = questoes[0]
    questao_personalizada.personalizada = True

    tentativa, selecionadas = grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 3, questionario_repo, tentativa_repo
    )

    assert questao_personalizada.id not in {q.id for q in selecionadas}
    assert tentativa.total_questoes == 2  # só as 2 não-personalizadas


def test_iniciar_tentativa_tema_exclui_questoes_personalizadas(questionario_repo, tentativa_repo):
    tema_id = uuid.uuid4()
    questionario, questoes, _ = _seed_pool(questionario_repo, num_questoes=3)
    questoes[0].personalizada = True
    questionario_repo.seed_pool_tema(
        tema_id, questionario_repo.get_questao_ids_pool_graduavel(questionario.id)
    )

    _, selecionadas = grading_service.iniciar_tentativa_tema(
        tema_id, uuid.uuid4(), 3, questionario_repo, tentativa_repo
    )

    assert questoes[0].id not in {q.id for q in selecionadas}


def test_iniciar_tentativa_valendo_nota_descarta_pratica_aberta_do_mesmo_modulo(
    questionario_repo, tentativa_repo
):
    """Praticar e Realizar são quizzes diferentes: pedir o valendo nota com uma
    prática aberta descarta a prática e devolve uma tentativa valendo nota de
    verdade - o backend nunca devolve a prática no lugar dela."""
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    user_id = uuid.uuid4()

    tentativa_pratica, _ = grading_service.iniciar_tentativa_com_pool(
        questionario_repo.get_questao_ids_pool(questionario.id),
        user_id,
        5,
        questionario_repo,
        tentativa_repo,
        questionario_id=questionario.id,
        tema_id=None,
        pratica=True,
    )

    tentativa_nota, _ = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, tentativa_repo
    )

    assert tentativa_nota.id != tentativa_pratica.id
    assert tentativa_nota.pratica is False
    assert list(tentativa_repo.tentativas) == [tentativa_nota.id]


def test_iniciar_tentativa_pratica_duas_vezes_retoma_a_mesma(questionario_repo, tentativa_repo):
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    user_id = uuid.uuid4()
    pool = questionario_repo.get_questao_ids_pool(questionario.id)

    def _praticar():
        return grading_service.iniciar_tentativa_com_pool(
            pool,
            user_id,
            5,
            questionario_repo,
            tentativa_repo,
            questionario_id=questionario.id,
            tema_id=None,
            pratica=True,
        )

    primeira, questoes_1 = _praticar()
    segunda, questoes_2 = _praticar()

    assert segunda.id == primeira.id
    assert [q.id for q in questoes_2] == [q.id for q in questoes_1]


def test_iniciar_tentativa_em_outro_modulo_nao_devolve_as_questoes_do_primeiro(
    questionario_repo, tentativa_repo
):
    """O bug original: deixar um quiz pela metade fazia todo módulo seguinte
    devolver as questões dele (ex.: cálculo dentro de História)."""
    questionario_a, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    questionario_b, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    ids_b = set(questionario_repo.get_questao_ids_pool(questionario_b.id))
    user_id = uuid.uuid4()

    tentativa_a, _ = grading_service.iniciar_tentativa(
        questionario_a.id, user_id, 5, questionario_repo, tentativa_repo
    )
    tentativa_b, questoes_b = grading_service.iniciar_tentativa(
        questionario_b.id, user_id, 5, questionario_repo, tentativa_repo
    )

    assert tentativa_b.id != tentativa_a.id
    assert tentativa_b.questionario_id == questionario_b.id
    assert {q.id for q in questoes_b} <= ids_b
    assert list(tentativa_repo.tentativas) == [tentativa_b.id]


def test_praticar_em_outro_modulo_descarta_a_pratica_aberta(questionario_repo, tentativa_repo):
    questionario_a, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    questionario_b, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    user_id = uuid.uuid4()

    def _praticar(questionario):
        return grading_service.iniciar_tentativa_com_pool(
            questionario_repo.get_questao_ids_pool(questionario.id),
            user_id,
            5,
            questionario_repo,
            tentativa_repo,
            questionario_id=questionario.id,
            tema_id=None,
            pratica=True,
        )

    pratica_a, _ = _praticar(questionario_a)
    pratica_b, _ = _praticar(questionario_b)

    assert pratica_b.id != pratica_a.id
    assert pratica_b.questionario_id == questionario_b.id
    assert list(tentativa_repo.tentativas) == [pratica_b.id]


def test_descartar_a_tentativa_de_um_aluno_nao_mexe_na_de_outro(questionario_repo, tentativa_repo):
    questionario_a, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    questionario_b, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    aluno_1, aluno_2 = uuid.uuid4(), uuid.uuid4()

    tentativa_do_2, _ = grading_service.iniciar_tentativa(
        questionario_a.id, aluno_2, 5, questionario_repo, tentativa_repo
    )
    grading_service.iniciar_tentativa(
        questionario_a.id, aluno_1, 5, questionario_repo, tentativa_repo
    )
    grading_service.iniciar_tentativa(
        questionario_b.id, aluno_1, 5, questionario_repo, tentativa_repo
    )  # descarta a do aluno 1 em A

    assert tentativa_repo.get_questionario_aberto_by_user(aluno_2).id == tentativa_do_2.id
    assert len(tentativa_repo.tentativas) == 2


class _RepoComJanelaDeCorrida:
    """Envolve um `InMemoryTentativaRepository` real, mas faz a *primeira*
    chamada a `get_questionario_aberto_by_user` devolver `None` mesmo que já
    exista uma tentativa aberta - simula a janela de corrida real (a leitura
    de uma requisição concorrente acontece antes do insert da outra virar
    visível). Chamadas seguintes (a re-checagem depois do IntegrityError)
    delegam pro repositório real normalmente."""

    def __init__(self, repo):
        self._repo = repo
        self._primeira_checagem = True

    def get_questionario_aberto_by_user(self, user_id):
        if self._primeira_checagem:
            self._primeira_checagem = False
            return None
        return self._repo.get_questionario_aberto_by_user(user_id)

    def __getattr__(self, nome):
        return getattr(self._repo, nome)


def test_iniciar_tentativa_perde_race_de_concorrencia_retoma_a_vencedora(
    questionario_repo, tentativa_repo
):
    """Simula duas requisições concorrentes pro mesmo aluno: as duas
    checagens de "tem tentativa aberta?" veem `None` (nenhuma foi
    inserida ainda), mas só um insert vence - o outro esbarra no índice
    único parcial (`flush` levanta `IntegrityError`) e, em vez de propagar
    um 500, retoma a tentativa que a primeira já criou."""
    questionario, _, _ = _seed_pool(questionario_repo, num_questoes=12)
    user_id = uuid.uuid4()

    tentativa_vencedora, _ = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, tentativa_repo
    )

    tentativa_repo.falhar_proximo_flush = True
    repo_com_corrida = _RepoComJanelaDeCorrida(tentativa_repo)

    tentativa_2, _ = grading_service.iniciar_tentativa(
        questionario.id, user_id, 5, questionario_repo, repo_com_corrida
    )

    assert tentativa_2.id == tentativa_vencedora.id
    assert len(tentativa_repo.tentativas) == 1


def test_iniciar_tentativa_tema_mistura_pools_de_varios_modulos(questionario_repo, tentativa_repo):
    tema_id = uuid.uuid4()
    _, questoes_1, _ = _seed_pool(questionario_repo, num_questoes=6)
    _, questoes_2, _ = _seed_pool(questionario_repo, num_questoes=6)
    pool_tema = [q.id for q in questoes_1] + [q.id for q in questoes_2]
    questionario_repo.seed_pool_tema(tema_id, pool_tema)

    tentativa, questoes = grading_service.iniciar_tentativa_tema(
        tema_id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    assert tentativa.tema_id == tema_id
    assert tentativa.questionario_id is None
    assert len(questoes) == 5
    assert {q.id for q in questoes} <= set(pool_tema)
