import uuid

import pytest

from app.core.exceptions import (
    LimiteQuestoesExcedidoException,
    ModuloNaoEncontradoException,
    QuestaoNaoEncontradaException,
    QuestionarioJaExisteException,
    QuestionarioNaoEncontradoException,
    QuestionarioSemQuestoesException,
)
from app.schemas.questionario import MAX_QUESTOES_POR_QUESTIONARIO
from app.services import quiz_manual_service
from app.services.quiz_manual_service import NovaQuestao
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.in_memory_repositories import (
    InMemoryModuloRepository,
    InMemoryQuestionarioRepository,
)


def _nova(enunciado="Quanto é 2 + 2?", correta="B") -> NovaQuestao:
    return NovaQuestao(
        enunciado=enunciado,
        alternativas=[{"letra": letra, "texto": f"opção {letra}"} for letra in "ABCDE"],
        explicacao="Porque sim.",
        resposta_correta=correta,
    )


@pytest.fixture
def modulo_repo() -> InMemoryModuloRepository:
    repo = InMemoryModuloRepository()
    repo.seed(ModuloBuilder().com_id(MODULO_ID).build())
    return repo


MODULO_ID = uuid.uuid4()


@pytest.fixture
def repo() -> InMemoryQuestionarioRepository:
    return InMemoryQuestionarioRepository()


def _criar(modulo_repo, repo, quantas=3):
    return quiz_manual_service.criar_questionario(
        MODULO_ID, [_nova(f"Pergunta {i}") for i in range(quantas)], modulo_repo, repo
    )


def test_criar_questionario_guarda_as_questoes_na_ordem_recebida(modulo_repo, repo):
    criadas = _criar(modulo_repo, repo, quantas=3)

    assert [q.enunciado for q, _ in criadas] == ["Pergunta 0", "Pergunta 1", "Pergunta 2"]
    assert [q.ordem for q, _ in criadas] == [0, 1, 2]
    questionario = repo.get_by_modulo(MODULO_ID)
    assert questionario.modelo_ia == "manual"
    assert all(q.questionario_id == questionario.id for q, _ in criadas)


def test_criar_questionario_grava_o_gabarito_de_cada_questao(modulo_repo, repo):
    criadas = quiz_manual_service.criar_questionario(
        MODULO_ID, [_nova(correta="A"), _nova(correta="E")], modulo_repo, repo
    )

    gabarito = repo.get_gabarito_map([q.id for q, _ in criadas])
    assert [gabarito[q.id] for q, _ in criadas] == ["A", "E"]
    assert [resposta for _, resposta in criadas] == ["A", "E"]


def test_criar_questionario_marca_questoes_como_nao_personalizadas(modulo_repo, repo):
    # a hand-written question is gradable: it must be in the graded pool
    criadas = _criar(modulo_repo, repo, quantas=2)

    questionario = repo.get_by_modulo(MODULO_ID)
    assert set(repo.get_questao_ids_pool_graduavel(questionario.id)) == {q.id for q, _ in criadas}


def test_criar_questionario_de_modulo_inexistente(repo):
    with pytest.raises(ModuloNaoEncontradoException):
        quiz_manual_service.criar_questionario(
            uuid.uuid4(), [_nova()], InMemoryModuloRepository(), repo
        )


def test_criar_questionario_quando_o_modulo_ja_tem_um(modulo_repo, repo):
    _criar(modulo_repo, repo)

    with pytest.raises(QuestionarioJaExisteException):
        _criar(modulo_repo, repo)


def test_criar_questionario_acima_do_limite(modulo_repo, repo):
    with pytest.raises(LimiteQuestoesExcedidoException):
        _criar(modulo_repo, repo, quantas=MAX_QUESTOES_POR_QUESTIONARIO + 1)

    assert repo.get_by_modulo(MODULO_ID) is None


def test_adicionar_questao_vai_para_o_fim(modulo_repo, repo):
    _criar(modulo_repo, repo, quantas=3)

    questao, resposta = quiz_manual_service.adicionar_questao(
        MODULO_ID, _nova("Última", correta="D"), modulo_repo, repo
    )

    assert questao.ordem == 3
    assert resposta == "D"
    assert repo.get_gabarito_map([questao.id])[questao.id] == "D"


def test_adicionar_questao_sem_questionario(modulo_repo, repo):
    with pytest.raises(QuestionarioNaoEncontradoException):
        quiz_manual_service.adicionar_questao(MODULO_ID, _nova(), modulo_repo, repo)


def test_adicionar_questao_acima_do_limite(modulo_repo, repo):
    _criar(modulo_repo, repo, quantas=MAX_QUESTOES_POR_QUESTIONARIO)

    with pytest.raises(LimiteQuestoesExcedidoException):
        quiz_manual_service.adicionar_questao(MODULO_ID, _nova(), modulo_repo, repo)


def test_remover_questao_mantem_a_ordem_relativa_das_outras(modulo_repo, repo):
    criadas = _criar(modulo_repo, repo, quantas=4)
    removida = criadas[1][0]

    quiz_manual_service.remover_questao(MODULO_ID, removida.id, modulo_repo, repo)

    restantes = repo.get_questoes_by_ids(
        repo.get_questao_ids_pool(repo.get_by_modulo(MODULO_ID).id)
    )
    assert sorted(q.ordem for q in restantes) == [0, 2, 3]
    assert removida.id not in repo.gabaritos  # the answer key goes with it


def test_questao_adicionada_depois_de_remover_nao_reaproveita_ordem(modulo_repo, repo):
    criadas = _criar(modulo_repo, repo, quantas=3)
    quiz_manual_service.remover_questao(MODULO_ID, criadas[2][0].id, modulo_repo, repo)

    nova, _ = quiz_manual_service.adicionar_questao(MODULO_ID, _nova(), modulo_repo, repo)

    assert nova.ordem == 2  # max + 1 of what is left (0 and 1), never a duplicate


def test_nao_remove_a_ultima_questao(modulo_repo, repo):
    criadas = _criar(modulo_repo, repo, quantas=1)

    with pytest.raises(QuestionarioSemQuestoesException):
        quiz_manual_service.remover_questao(MODULO_ID, criadas[0][0].id, modulo_repo, repo)

    assert len(repo.get_questao_ids_pool(repo.get_by_modulo(MODULO_ID).id)) == 1


def test_remover_questao_de_outro_questionario(modulo_repo, repo):
    _criar(modulo_repo, repo)
    outro_modulo = uuid.uuid4()
    modulo_repo.seed(ModuloBuilder().com_id(outro_modulo).build())
    alheia = quiz_manual_service.criar_questionario(
        outro_modulo, [_nova(), _nova()], modulo_repo, repo
    )[0][0]

    with pytest.raises(QuestaoNaoEncontradaException):
        quiz_manual_service.remover_questao(MODULO_ID, alheia.id, modulo_repo, repo)

    assert alheia.id in repo.questoes  # untouched


def test_remover_questao_inexistente(modulo_repo, repo):
    _criar(modulo_repo, repo)

    with pytest.raises(QuestaoNaoEncontradaException):
        quiz_manual_service.remover_questao(MODULO_ID, uuid.uuid4(), modulo_repo, repo)


def test_remover_questionario_leva_questoes_e_gabaritos(modulo_repo, repo):
    _criar(modulo_repo, repo, quantas=3)

    quiz_manual_service.remover_questionario(MODULO_ID, modulo_repo, repo)

    assert repo.get_by_modulo(MODULO_ID) is None
    assert repo.questoes == {}
    assert repo.gabaritos == {}


def test_remover_questionario_inexistente(modulo_repo, repo):
    with pytest.raises(QuestionarioNaoEncontradoException):
        quiz_manual_service.remover_questionario(MODULO_ID, modulo_repo, repo)


def test_pode_recriar_o_questionario_depois_de_remover(modulo_repo, repo):
    _criar(modulo_repo, repo)
    quiz_manual_service.remover_questionario(MODULO_ID, modulo_repo, repo)

    criadas = _criar(modulo_repo, repo, quantas=2)

    assert [q.ordem for q, _ in criadas] == [0, 1]
