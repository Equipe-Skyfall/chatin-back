import uuid

import pytest

from app.core.exceptions import ConteudoIndisponivelException, GeracaoConteudoFalhouException
from app.models.modulo import STATUS_ERRO, STATUS_PRONTO
from app.services.questionario_pipeline import gerar_questionario_modulo
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.in_memory_repositories import (
    InMemoryModuloRepository,
    InMemoryQuestionarioRepository,
)


def test_gera_pool_de_questoes_uma_unica_chamada_de_ia(fake_ai_provider):
    modulo = ModuloBuilder().com_conteudo("Conteúdo de teste do módulo.").build()
    questionario_repo = InMemoryQuestionarioRepository()
    modulo_repo = InMemoryModuloRepository()

    gerar_questionario_modulo(
        modulo, questionario_repo, modulo_repo, fake_ai_provider, pool_size=12
    )

    assert fake_ai_provider.gerar_questionario_calls == 1
    assert modulo.status == STATUS_PRONTO
    questionario = questionario_repo.get_by_modulo(modulo.id)
    pool_ids = questionario_repo.get_questao_ids_pool(questionario.id)
    assert len(pool_ids) == 12
    assert len(questionario_repo.get_gabarito_map(pool_ids)) == 12


def test_duas_tentativas_no_mesmo_modulo_nao_geram_nova_chamada_de_ia(fake_ai_provider):
    """The actual token-savings guarantee: sampling for attempts is DB-only and
    never touches the AI provider again after the pool is generated once."""
    from app.services import grading_service
    from tests.fakes.in_memory_repositories import InMemoryTentativaRepository

    modulo = ModuloBuilder().com_conteudo("Conteúdo de teste do módulo.").build()
    questionario_repo = InMemoryQuestionarioRepository()
    modulo_repo = InMemoryModuloRepository()

    gerar_questionario_modulo(
        modulo, questionario_repo, modulo_repo, fake_ai_provider, pool_size=12
    )
    assert fake_ai_provider.gerar_questionario_calls == 1

    tentativa_repo = InMemoryTentativaRepository()
    questionario = questionario_repo.get_by_modulo(modulo.id)
    grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )
    grading_service.iniciar_tentativa(
        questionario.id, uuid.uuid4(), 5, questionario_repo, tentativa_repo
    )

    assert fake_ai_provider.gerar_questionario_calls == 1


def test_modulo_sem_conteudo_levanta_excecao(fake_ai_provider):
    modulo = ModuloBuilder().com_conteudo(None).build()
    questionario_repo = InMemoryQuestionarioRepository()
    modulo_repo = InMemoryModuloRepository()

    with pytest.raises(ConteudoIndisponivelException):
        gerar_questionario_modulo(
            modulo, questionario_repo, modulo_repo, fake_ai_provider, pool_size=12
        )


def test_falha_do_provedor_marca_modulo_como_erro(fake_ai_provider):
    fake_ai_provider.falhar_gerar_questionario = True
    modulo = ModuloBuilder().com_conteudo("Conteúdo de teste do módulo.").build()
    questionario_repo = InMemoryQuestionarioRepository()
    modulo_repo = InMemoryModuloRepository()

    with pytest.raises(GeracaoConteudoFalhouException):
        gerar_questionario_modulo(
            modulo, questionario_repo, modulo_repo, fake_ai_provider, pool_size=12
        )

    assert modulo.status == STATUS_ERRO
