import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConversaOcupadaException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.services import chat_aluno_service
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.in_memory_repositories import InMemoryConversaRepository, InMemoryModuloRepository


def _conversa(modulo_id=None, n_mensagens: int = 0) -> Conversa:
    conversa = Conversa(id=uuid.uuid4(), user_id="user-1", tipo=TIPO_ALUNO, modulo_id=modulo_id)
    conversa.updated_at = datetime.now(UTC)
    conversa.mensagens = [
        Mensagem(
            conversa_id=conversa.id,
            papel=PAPEL_USUARIO if i % 2 == 0 else PAPEL_ASSISTENTE,
            conteudo=f"mensagem {i}",
            ordem=i,
        )
        for i in range(n_mensagens)
    ]
    return conversa


def test_persiste_pergunta_e_resposta(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    resposta = chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, 20
    )

    assert resposta == "Resposta de teste para: oi"
    assert [(m.papel, m.conteudo) for m in conversa.mensagens] == [
        (PAPEL_USUARIO, "oi"),
        (PAPEL_ASSISTENTE, "Resposta de teste para: oi"),
    ]


def test_envia_so_a_janela_mais_recente_sem_a_pergunta_atual(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=30)
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa, "nova pergunta", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, 20
    )

    (historico,) = fake_ai_provider.historicos_recebidos
    assert [m.conteudo for m in historico] == [f"mensagem {i}" for i in range(10, 30)]


def test_historico_curto_e_enviado_inteiro(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=4)
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, 20
    )

    (historico,) = fake_ai_provider.historicos_recebidos
    assert [m.conteudo for m in historico] == [f"mensagem {i}" for i in range(4)]


def test_conversa_de_modulo_repassa_o_conteudo_do_modulo(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(ModuloBuilder().com_id(modulo_id).com_conteudo("texto do módulo").build())

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, 20
    )

    assert fake_ai_provider.conteudos_modulo_recebidos == ["texto do módulo"]


def test_conversa_sem_modulo_nao_repassa_conteudo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, 20
    )

    assert fake_ai_provider.conteudos_modulo_recebidos == [None]


def test_colisao_de_ordem_vira_conversa_ocupada_sem_chamar_a_ia(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    conversa_repo.falhar_proximo_commit = True

    with pytest.raises(ConversaOcupadaException):
        chat_aluno_service.enviar_mensagem(
            conversa, "oi", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, 20
        )

    assert conversa_repo.rollbacks == 1
    assert fake_ai_provider.responder_pergunta_aluno_calls == 0
    assert conversa.mensagens == []
