import uuid
from datetime import UTC, datetime

import pytest

from app.ai.prompts import LICAO_MARCADOR
from app.ai.schemas import FerramentaContexto, MensagemHistorico
from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
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


def _ctx(conversa_id: uuid.UUID) -> FerramentaContexto:
    """Repos here are never touched by `chat_aluno_service` itself - it only
    threads `ctx` through to the (fake) AI provider, which just records it -
    so `None` stands in fine for everything but the identity fields."""
    return FerramentaContexto(
        materia_repo=None,
        tema_repo=None,
        modulo_repo=None,
        questionario_repo=None,
        xp_repo=None,
        tentativa_repo=None,
        progresso_repo=None,
        voto_repo=None,
        ai_provider=None,
        pool_size=12,
        user_id="user-1",
        conversa_id=conversa_id,
    )


def test_persiste_pergunta_e_resposta(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    resposta = chat_aluno_service.enviar_mensagem(
        conversa,
        "oi",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
    )

    assert resposta == "Resposta de teste para: oi"
    assert [(m.papel, m.conteudo) for m in conversa.mensagens] == [
        (PAPEL_USUARIO, "oi"),
        (PAPEL_ASSISTENTE, "Resposta de teste para: oi"),
    ]


def test_janela_inclui_a_pergunta_atual_e_corta_as_mais_antigas(fake_ai_provider):
    """`mensagens` passed to the provider ends with the current turn (same
    convention as the admin agent, whose ADK path reads `mensagens[-1]` as
    the new message) - the window is the most recent `janela` messages
    *including* it, not `janela` messages of prior history plus the new one
    on top."""
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=30)
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa,
        "nova pergunta",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
    )

    (historico,) = fake_ai_provider.historicos_recebidos
    assert [m.conteudo for m in historico] == [
        *[f"mensagem {i}" for i in range(11, 30)],
        "nova pergunta",
    ]


def test_historico_curto_e_enviado_inteiro(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=4)
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa,
        "oi",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
    )

    (historico,) = fake_ai_provider.historicos_recebidos
    assert [m.conteudo for m in historico] == [*[f"mensagem {i}" for i in range(4)], "oi"]


def test_conversa_de_modulo_repassa_o_conteudo_do_modulo(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(ModuloBuilder().com_id(modulo_id).com_conteudo("texto do módulo").build())

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, modulo_repo, fake_ai_provider, _ctx(conversa.id), 20
    )

    assert fake_ai_provider.conteudos_modulo_recebidos == ["texto do módulo"]


def test_conversa_sem_modulo_nao_repassa_conteudo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa,
        "oi",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
    )

    assert fake_ai_provider.conteudos_modulo_recebidos == [None]


def test_ctx_repassado_ao_provider_e_o_mesmo_da_conversa(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    ctx = _ctx(conversa.id)

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, InMemoryModuloRepository(), fake_ai_provider, ctx, 20
    )

    assert fake_ai_provider.ctx_recebido is ctx


def test_colisao_de_ordem_vira_conversa_ocupada_sem_chamar_a_ia(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    conversa_repo.falhar_proximo_commit = True

    with pytest.raises(ConversaOcupadaException):
        chat_aluno_service.enviar_mensagem(
            conversa,
            "oi",
            conversa_repo,
            InMemoryModuloRepository(),
            fake_ai_provider,
            _ctx(conversa.id),
            20,
        )

    assert conversa_repo.rollbacks == 1
    assert fake_ai_provider.conversar_com_agente_aluno_calls == 0
    assert conversa.mensagens == []


# --- obter_ou_gerar_resumo ---


def test_obter_ou_gerar_resumo_gera_quando_ausente(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa_repo.add(conversa)

    resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)

    assert resumo == "Resumo de teste da conversa."
    assert conversa.resumo == "Resumo de teste da conversa."
    assert conversa.resumo_gerado_em is not None


def test_obter_ou_gerar_resumo_ia_falha_sem_resumo_anterior_retorna_none(
    fake_ai_provider, monkeypatch
):
    """A empty/failed candidate from Gemini (a real, observed failure mode -
    `finish_reason=STOP` with no content) must not break the whole
    `/chat/resumos` list for every other conversation (RNF6)."""
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa_repo.add(conversa)

    def _falhar(_mensagens):
        raise ProvedorIAIndisponivelException("O provedor de IA retornou um resumo vazio.")

    monkeypatch.setattr(fake_ai_provider, "resumir_conversa", _falhar)

    resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)

    assert resumo is None
    assert conversa.resumo_gerado_em is None


def test_obter_ou_gerar_resumo_ia_falha_mantem_resumo_anterior(fake_ai_provider, monkeypatch):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa.resumo = "Resumo antigo."
    conversa.resumo_gerado_em = datetime(2020, 1, 1, tzinfo=UTC)  # stale on purpose
    conversa_repo.add(conversa)

    def _falhar(_mensagens):
        raise ProvedorIAIndisponivelException("O provedor de IA retornou um resumo vazio.")

    monkeypatch.setattr(fake_ai_provider, "resumir_conversa", _falhar)

    resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)

    assert resumo == "Resumo antigo."


def test_obter_ou_gerar_resumo_nao_chama_a_ia_quando_ela_esta_fora_do_ar(fake_ai_provider):
    from app.ai.disponibilidade import status_ia

    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa_repo.add(conversa)
    status_ia.marcar_indisponivel()

    resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)

    assert resumo is None
    assert fake_ai_provider.resumir_conversa_calls == 0
    assert conversa.resumo_gerado_em is None


def test_obter_ou_gerar_resumo_com_ia_fora_do_ar_devolve_o_resumo_guardado(fake_ai_provider):
    from app.ai.disponibilidade import status_ia

    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa.resumo = "Resumo antigo."
    conversa.resumo_gerado_em = datetime(2020, 1, 1, tzinfo=UTC)  # stale on purpose
    conversa_repo.add(conversa)
    status_ia.marcar_indisponivel()

    resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)

    assert resumo == "Resumo antigo."
    assert fake_ai_provider.resumir_conversa_calls == 0


def test_obter_ou_gerar_resumo_atualizado_nao_depende_do_estado_da_ia(fake_ai_provider):
    from app.ai.disponibilidade import status_ia

    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=2)
    conversa.resumo = "Resumo em dia."
    conversa.resumo_gerado_em = datetime(2999, 1, 1, tzinfo=UTC)
    conversa_repo.add(conversa)
    status_ia.marcar_indisponivel()

    assert (
        chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, fake_ai_provider)
        == "Resumo em dia."
    )


def _licao_setup():
    modulo = ModuloBuilder().com_titulo("Causas").build()
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(modulo)
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(modulo_id=modulo.id)
    conversa_repo.add(conversa)
    return modulo, modulo_repo, conversa_repo, conversa


def test_enviar_licao_salva_so_a_resposta_e_marca_start_lesson(fake_ai_provider, licao_repo):
    modulo, modulo_repo, conversa_repo, conversa = _licao_setup()

    resposta = chat_aluno_service.enviar_licao(
        conversa,
        "user-1",
        conversa_repo,
        modulo_repo,
        licao_repo,
        fake_ai_provider,
        _ctx(conversa.id),
    )

    assert resposta is not None
    assert [(m.papel, m.conteudo) for m in conversa.mensagens] == [(PAPEL_ASSISTENTE, resposta)]
    assert licao_repo.existe("user-1", modulo.id)
    pedido = fake_ai_provider.historicos_recebidos[0][-1]
    assert pedido.conteudo.startswith(LICAO_MARCADOR)
    assert fake_ai_provider.conteudos_modulo_recebidos == [modulo.conteudo]


def test_enviar_licao_nao_repete_quando_ja_enviada(fake_ai_provider, licao_repo):
    modulo, modulo_repo, conversa_repo, conversa = _licao_setup()
    licao_repo.marcar("user-1", modulo.id)

    resposta = chat_aluno_service.enviar_licao(
        conversa,
        "user-1",
        conversa_repo,
        modulo_repo,
        licao_repo,
        fake_ai_provider,
        _ctx(conversa.id),
    )

    assert resposta is None
    assert fake_ai_provider.conversar_com_agente_aluno_calls == 0
    assert conversa.mensagens == []


def test_enviar_licao_falha_da_ia_nao_marca_start_lesson(fake_ai_provider, licao_repo):
    modulo, modulo_repo, conversa_repo, conversa = _licao_setup()
    fake_ai_provider.falhar_conversar_com_agente_aluno = True

    with pytest.raises(RuntimeError):
        chat_aluno_service.enviar_licao(
            conversa,
            "user-1",
            conversa_repo,
            modulo_repo,
            licao_repo,
            fake_ai_provider,
            _ctx(conversa.id),
        )

    assert not licao_repo.existe("user-1", modulo.id)
    assert conversa.mensagens == []


def test_historico_oculta_o_turno_sintetico_da_licao():
    historico = [
        MensagemHistorico(
            id=uuid.uuid4(),
            papel=PAPEL_USUARIO,
            conteudo=f"{LICAO_MARCADOR} dê a aula",
            chamadas_ferramentas=None,
            created_at=datetime.now(UTC),
        ),
        MensagemHistorico(
            id=uuid.uuid4(),
            papel=PAPEL_ASSISTENTE,
            conteudo="Aula completa. Alguma dúvida?",
            chamadas_ferramentas=None,
            created_at=datetime.now(UTC),
        ),
    ]

    resultado = chat_aluno_service.anexar_fontes_ao_historico(historico, [])

    assert [m.papel for m in resultado] == [PAPEL_ASSISTENTE]


def test_enviar_licao_com_ia_fora_do_ar_marca_a_ia_indisponivel(fake_ai_provider, licao_repo):
    from app.ai.disponibilidade import status_ia
    from app.core.exceptions import ProvedorIAIndisponivelException

    class _IAFora(type(fake_ai_provider)):
        def conversar_com_agente_aluno(self, *args, **kwargs):
            raise ProvedorIAIndisponivelException("503")

    modulo, modulo_repo, conversa_repo, conversa = _licao_setup()
    assert status_ia.disponivel()

    with pytest.raises(ProvedorIAIndisponivelException):
        chat_aluno_service.enviar_licao(
            conversa, "user-1", conversa_repo, modulo_repo, licao_repo, _IAFora(), _ctx(conversa.id)
        )

    assert not status_ia.disponivel()
    assert not licao_repo.existe("user-1", modulo.id)
