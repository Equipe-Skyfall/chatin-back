import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
from app.models.conversa import TIPO_ALUNO, Conversa
from app.services import chat_aluno_service
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.fake_redis import FakeRedisCliente
from tests.fakes.in_memory_repositories import InMemoryConversaRepository, InMemoryModuloRepository


def _conversa(modulo_id=None) -> Conversa:
    conversa = Conversa(id=uuid.uuid4(), user_id="user-1", tipo=TIPO_ALUNO, modulo_id=modulo_id)
    conversa.mensagens = []
    conversa.updated_at = datetime.now(UTC)
    return conversa


def test_enviar_mensagem_sem_modulo_nao_busca_memoria_longo_prazo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()

    resposta = chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, None, 20, 3
    )

    assert resposta == "Resposta de teste para: oi"
    assert fake_ai_provider.gerar_embedding_calls == 0
    assert fake_ai_provider.memorias_relevantes_recebidas == [None]


def test_lock_ocupado_levanta_excecao(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()
    redis_cliente = FakeRedisCliente()
    redis_cliente.set(f"conversa:{conversa.id}:lock", "1", nx=True)

    with pytest.raises(ConversaOcupadaException):
        chat_aluno_service.enviar_mensagem(
            conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, redis_cliente, 20, 3
        )


def test_lock_e_liberado_apos_o_turno(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()
    redis_cliente = FakeRedisCliente()

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, redis_cliente, 20, 3
    )

    # se o lock não tivesse sido liberado, essa segunda chamada levantaria
    chat_aluno_service.enviar_mensagem(
        conversa,
        "outra pergunta",
        conversa_repo,
        modulo_repo,
        fake_ai_provider,
        redis_cliente,
        20,
        3,
    )


def test_com_modulo_busca_e_repassa_memorias_relevantes(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa_atual = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa_atual)

    fake_ai_provider.embeddings_fixos["pergunta sobre limite lateral"] = [1.0, 0.0]

    # outra conversa antiga do mesmo módulo, já com memória indexada (usa o
    # mesmo vetor fixo acima, pra garantir que é a mais próxima da pergunta)
    outra = _conversa(modulo_id=modulo_id)
    outra.mensagens = []
    outra.memoria_chave = "aluno tem dificuldade com limites laterais"
    outra.memoria_embedding = fake_ai_provider.gerar_embedding("pergunta sobre limite lateral")
    outra.memoria_gerada_em = datetime.now(UTC)
    conversa_repo.add(outra)
    fake_ai_provider.gerar_embedding_calls = 0  # reseta o call count usado pra seedar acima

    modulo_repo = InMemoryModuloRepository()
    modulo = ModuloBuilder().com_id(modulo_id).build()
    modulo_repo.seed(modulo)

    chat_aluno_service.enviar_mensagem(
        conversa_atual,
        "pergunta sobre limite lateral",
        conversa_repo,
        modulo_repo,
        fake_ai_provider,
        None,
        20,
        3,
    )

    assert fake_ai_provider.memorias_relevantes_recebidas == [
        ["aluno tem dificuldade com limites laterais"]
    ]


def test_falha_no_embedding_nao_quebra_o_turno(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(ModuloBuilder().com_id(modulo_id).build())

    # o AIProvider real (GeminiProvider) sempre traduz falha de rede/SDK pra
    # essa exceção de domínio - é o que `_memorias_relevantes` sabe tratar
    # (RNF6: degrada pra "sem contexto de longo prazo", não quebra o turno).
    def _gerar_embedding_com_falha(texto: str) -> list[float]:
        raise ProvedorIAIndisponivelException("falha simulada")

    fake_ai_provider.gerar_embedding = _gerar_embedding_com_falha

    resposta = chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, None, 20, 3
    )

    assert resposta == "Resposta de teste para: oi"
    assert fake_ai_provider.memorias_relevantes_recebidas == [None]
