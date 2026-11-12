import uuid
from datetime import UTC, datetime

import pytest

from app.ai.prompts import LICAO_MARCADOR
from app.ai.schemas import FerramentaContexto, MensagemHistorico
from app.core.exceptions import ConversaOcupadaException, ProvedorIAIndisponivelException
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.services import chat_aluno_service
from tests.builders.modulo_builder import ModuloBuilder
from tests.fakes.in_memory_repositories import (
    InMemoryConversaRepository,
    InMemoryModuloRepository,
    InMemoryResumoAlunoRepository,
)


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


# --- resposta_pronta (chat shortcut) ---


def test_enviar_mensagem_com_resposta_pronta_nao_chama_o_agente(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    resposta = chat_aluno_service.enviar_mensagem(
        conversa,
        "como estou indo?",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        janela=20,
        resposta_pronta="Você tem 120 XP.",
    )

    assert resposta == "Você tem 120 XP."
    assert fake_ai_provider.conversar_com_agente_aluno_calls == 0
    assert [(m.papel, m.conteudo) for m in conversa.mensagens] == [
        (PAPEL_USUARIO, "como estou indo?"),
        (PAPEL_ASSISTENTE, "Você tem 120 XP."),
    ]
    assert fake_ai_provider.trocas_registradas == [
        (conversa.id, "como estou indo?", "Você tem 120 XP.")
    ]


def test_enviar_mensagem_sem_resposta_pronta_continua_usando_o_agente(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa,
        "explique a revolução francesa",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        janela=20,
    )

    assert fake_ai_provider.conversar_com_agente_aluno_calls == 1
    assert fake_ai_provider.trocas_registradas == []


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


# --- the student's running summary (`ResumoAluno`) ---------------------------


def _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo, texto="oi", **kw):
    return chat_aluno_service.enviar_mensagem(
        conversa,
        texto,
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
        resumo_repo=resumo_repo,
        janela_com_resumo=kw.get("janela_com_resumo", 4),
        resumo_a_cada=kw.get("resumo_a_cada", 6),
    )


def test_sem_resumo_usa_a_janela_normal_e_nao_manda_resumo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)

    _enviar(conversa, conversa_repo, fake_ai_provider, InMemoryResumoAlunoRepository())

    assert fake_ai_provider.resumos_aluno_recebidos == [None]
    assert len(fake_ai_provider.historicos_recebidos[0]) == 11  # all 10 + the new question


def test_com_resumo_envia_o_resumo_e_so_as_mensagens_recentes(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()
    resumo_repo.salvar("user-1", "O aluno estuda logaritmos.", {str(conversa.id): 10})

    _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)

    assert fake_ai_provider.resumos_aluno_recebidos == ["O aluno estuda logaritmos."]
    historico = fake_ai_provider.historicos_recebidos[0]
    assert len(historico) == 4
    assert historico[-1].conteudo == "oi"


def test_resumo_de_outro_aluno_nao_e_usado(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()
    resumo_repo.salvar("outro-aluno", "Segredo do outro aluno.", {})

    _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)

    assert fake_ai_provider.resumos_aluno_recebidos == [None]


def test_nao_atualiza_o_resumo_antes_de_juntar_mensagens_suficientes(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()

    _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)  # 2 messages < 6

    assert fake_ai_provider.resumir_historico_aluno_calls == []
    assert resumo_repo.get_by_user("user-1") is None


def test_atualiza_o_resumo_ao_juntar_mensagens_suficientes(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=4)
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()

    _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)  # 4 + 2 = 6

    anterior, enviadas = fake_ai_provider.resumir_historico_aluno_calls[0]
    assert anterior is None
    assert len(enviadas) == 6
    salvo = resumo_repo.get_by_user("user-1")
    assert salvo.resumo == "Resumo do aluno (1)"
    assert salvo.mensagens_resumidas == {str(conversa.id): 6}


def test_atualizacao_manda_so_o_que_o_resumo_ainda_nao_cobre(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()
    resumo_repo.salvar("user-1", "Resumo antigo.", {str(conversa.id): 4})

    _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)  # 12 - 4 = 8 new

    anterior, enviadas = fake_ai_provider.resumir_historico_aluno_calls[0]
    assert anterior == "Resumo antigo."
    assert [m.conteudo for m in enviadas][0] == "mensagem 4"
    assert resumo_repo.get_by_user("user-1").mensagens_resumidas == {str(conversa.id): 12}


def test_resumo_cobre_conversas_diferentes_sem_perder_o_progresso_de_cada_uma(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    outra = _conversa(n_mensagens=4)
    atual = _conversa(n_mensagens=4)
    conversa_repo.add(outra)
    conversa_repo.add(atual)
    resumo_repo = InMemoryResumoAlunoRepository()
    resumo_repo.salvar("user-1", "Resumo.", {str(outra.id): 4})

    _enviar(atual, conversa_repo, fake_ai_provider, resumo_repo)

    assert resumo_repo.get_by_user("user-1").mensagens_resumidas == {
        str(outra.id): 4,
        str(atual.id): 6,
    }


def test_falha_ao_atualizar_o_resumo_mantem_o_anterior_e_nao_quebra_o_chat(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()
    resumo_repo.salvar("user-1", "Resumo antigo.", {str(conversa.id): 4})
    fake_ai_provider.falhar_resumir_historico_aluno = True

    resposta = _enviar(conversa, conversa_repo, fake_ai_provider, resumo_repo)

    assert resposta  # the chat answered anyway
    salvo = resumo_repo.get_by_user("user-1")
    assert salvo.resumo == "Resumo antigo."
    assert salvo.mensagens_resumidas == {str(conversa.id): 4}  # retried next turn


def test_atalho_nao_atualiza_o_resumo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)
    resumo_repo = InMemoryResumoAlunoRepository()

    chat_aluno_service.enviar_mensagem(
        conversa,
        "como estou indo?",
        conversa_repo,
        InMemoryModuloRepository(),
        fake_ai_provider,
        _ctx(conversa.id),
        20,
        resposta_pronta="Você está indo bem.",
        resumo_repo=resumo_repo,
        resumo_a_cada=2,
    )

    assert fake_ai_provider.resumir_historico_aluno_calls == []
    assert fake_ai_provider.conversar_com_agente_aluno_calls == 0


def test_atualizar_resumo_ignora_conversa_de_outro_aluno(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(n_mensagens=10)
    conversa_repo.add(conversa)

    atualizado = chat_aluno_service.atualizar_resumo_aluno(
        "outro-aluno",
        conversa.id,
        conversa_repo,
        InMemoryResumoAlunoRepository(),
        fake_ai_provider,
        2,
    )

    assert atualizado is False
    assert fake_ai_provider.resumir_historico_aluno_calls == []
