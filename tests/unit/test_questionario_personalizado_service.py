import uuid

import pytest

from app.core.exceptions import GeracaoConteudoFalhouException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.services import questionario_personalizado_service
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.questionario_builder import QuestionarioBuilder
from tests.fakes.in_memory_repositories import (
    InMemoryConversaRepository,
    InMemoryModuloRepository,
    InMemoryTentativaRepository,
)


def _setup(questionario_repo, num_questoes_existentes=12):
    modulo_id = uuid.uuid4()
    modulo = ModuloBuilder().com_id(modulo_id).com_conteudo("Conteúdo de teste.").build()
    questionario, questoes, gabarito_map = (
        QuestionarioBuilder()
        .com_modulo_id(modulo_id)
        .com_num_questoes(num_questoes_existentes)
        .build()
    )
    questionario_repo.seed(questionario, questoes, gabarito_map)

    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(modulo)
    return modulo, questionario, modulo_repo


def test_pool_ja_suficiente_nao_chama_ia(questionario_repo, fake_ai_provider):
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=12)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()

    tentativa, questoes = questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    assert fake_ai_provider.gerar_questionario_calls == 0
    assert len(questoes) == 5
    assert tentativa.pratica is True


def test_pool_insuficiente_gera_so_a_diferenca_e_persiste_no_mesmo_pool(
    questionario_repo, fake_ai_provider
):
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=3)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()

    questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    assert fake_ai_provider.gerar_questionario_calls == 1
    pool_ids = questionario_repo.get_questao_ids_pool(questionario.id)
    assert len(pool_ids) == 12  # 3 já existentes + 9 geradas


def test_segunda_chamada_nao_gera_de_novo_apos_pool_completo(questionario_repo, fake_ai_provider):
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=3)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()

    questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )
    # conclui a tentativa em andamento pra poder iniciar outra (limite de 1 ativa)
    tentativa_repo.marcar_concluida(next(iter(tentativa_repo.tentativas.values())), 100.0, 5)

    questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-2",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    assert fake_ai_provider.gerar_questionario_calls == 1


def test_usa_conversa_do_aluno_como_contexto(questionario_repo, fake_ai_provider):
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=3)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()
    conversa = Conversa(
        id=uuid.uuid4(),
        user_id="user-1",
        tipo=TIPO_ALUNO,
        modulo_id=questionario.modulo_id,
    )
    conversa.mensagens = [
        Mensagem(conversa_id=conversa.id, papel=PAPEL_USUARIO, conteudo="O que é limite lateral?"),
        Mensagem(conversa_id=conversa.id, papel=PAPEL_ASSISTENTE, conteudo="É quando..."),
    ]
    conversa_repo.seed(conversa)

    questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    assert any(
        c is not None and "limite lateral" in c
        for c in fake_ai_provider.contextos_conversa_recebidos
    )


def test_questoes_geradas_ficam_marcadas_personalizada(questionario_repo, fake_ai_provider):
    """As questões geradas sob demanda nunca podem ser sorteadas pelo
    questionário valendo nota - ver `get_questao_ids_pool_graduavel`."""
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=3)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()

    questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        12,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    todas = questionario_repo.get_questao_ids_pool(questionario.id)
    graduaveis = questionario_repo.get_questao_ids_pool_graduavel(questionario.id)
    assert len(todas) == 12
    assert len(graduaveis) == 3  # só as 3 originais - as 9 novas são personalizada=True
    novas = questionario_repo.get_questoes_by_ids(set(todas) - set(graduaveis))
    assert all(q.personalizada for q in novas)


def test_tentativa_aberta_evita_chamada_de_ia(questionario_repo, fake_ai_provider):
    """Ordem importa: se o aluno já tem um questionário aberto, a checagem
    precisa vir *antes* de qualquer chamada de IA - senão paga o custo de
    gerar questões novas só pra descartar a resposta em favor da aberta."""
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=1)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()
    user_id = "user-1"

    tentativa_aberta, _ = questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        user_id,
        1,
        1,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )
    assert fake_ai_provider.gerar_questionario_calls == 0  # pool já tinha 1, não precisou gerar

    # pool pequeno de propósito - se a checagem de tentativa aberta viesse
    # depois da geração, essa segunda chamada dispararia gerar_questionario
    tentativa_2, _ = questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        user_id,
        12,  # pool_minimo bem maior que o que existe - geraria 11 questões
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )

    assert tentativa_2.id == tentativa_aberta.id
    assert fake_ai_provider.gerar_questionario_calls == 0


def test_falha_na_geracao_faz_rollback_sem_deixar_pool_parcial(questionario_repo, fake_ai_provider):
    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=3)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()
    fake_ai_provider.falhar_gerar_questionario = True

    with pytest.raises(GeracaoConteudoFalhouException):
        questionario_personalizado_service.gerar_tentativa_personalizada(
            questionario.modulo_id,
            "user-1",
            12,
            5,
            modulo_repo,
            questionario_repo,
            conversa_repo,
            tentativa_repo,
            fake_ai_provider,
        )

    # nenhuma questão nova deve ter ficado meio-persistida
    assert len(questionario_repo.get_questao_ids_pool(questionario.id)) == 3


def test_nao_conta_para_progresso_ao_responder(questionario_repo, fake_ai_provider):
    from app.schemas.tentativa import RespostaInput
    from app.services import grading_service

    _, questionario, modulo_repo = _setup(questionario_repo, num_questoes_existentes=5)
    tentativa_repo = InMemoryTentativaRepository()
    conversa_repo = InMemoryConversaRepository()

    tentativa, questoes = questionario_personalizado_service.gerar_tentativa_personalizada(
        questionario.modulo_id,
        "user-1",
        5,
        5,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        fake_ai_provider,
    )
    respostas = [RespostaInput(questao_id=q.id, resposta_escolhida="A") for q in questoes]

    tentativa, _ = grading_service.responder_tentativa(
        tentativa, respostas, questionario_repo, tentativa_repo
    )

    # o router só chama `atualizar_progresso` quando `questionario_id is not
    # None and not tentativa.pratica` - aqui `pratica` é True, então mesmo
    # sendo módulo-scoped o progresso não seria atualizado.
    assert tentativa.pratica is True
    assert tentativa.questionario_id == questionario.id
