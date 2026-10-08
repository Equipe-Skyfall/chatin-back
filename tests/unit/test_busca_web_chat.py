import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.ai.adk_tools import MAX_BUSCAS_WEB_POR_TURNO, construir_tools_aluno
from app.ai.grounding import fontes_web_a_partir_do_grounding, resolver_redirect
from app.ai.schemas import FerramentaContexto, MensagemHistorico, ResultadoBuscaWeb
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.services import chat_aluno_service
from tests.fakes.in_memory_repositories import InMemoryConversaRepository, InMemoryModuloRepository


def _ctx(ai_provider, conversa_id=None) -> FerramentaContexto:
    return FerramentaContexto(
        materia_repo=None,
        tema_repo=None,
        modulo_repo=None,
        questionario_repo=None,
        xp_repo=None,
        progresso_repo=None,
        voto_repo=None,
        ai_provider=ai_provider,
        pool_size=12,
        user_id="user-1",
        conversa_id=conversa_id or uuid.uuid4(),
    )


def _chunk(uri, title=None, domain=None):
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title, domain=domain))


def _conversa() -> Conversa:
    conversa = Conversa(id=uuid.uuid4(), user_id="user-1", tipo=TIPO_ALUNO)
    conversa.updated_at = datetime.now(UTC)
    conversa.mensagens = []
    return conversa


# --- grounding -> FonteWeb ---


def test_grounding_resolve_redirect_deduplica_e_descarta_chunk_sem_link():
    chunks = [
        _chunk("https://redirect/1", title="Brasil Escola", domain="brasilescola.uol.com.br"),
        _chunk("https://redirect/2", title="Duplicada"),
        _chunk(None, title="Sem link"),
    ]
    resolver = lambda url: "https://real.org/pagina"  # noqa: E731

    fontes = fontes_web_a_partir_do_grounding(chunks, "revolução francesa", resolver)

    assert len(fontes) == 1
    assert fontes[0].url == "https://real.org/pagina"
    assert fontes[0].titulo == "Brasil Escola"
    assert fontes[0].consulta == "revolução francesa"


def test_grounding_titulo_cai_para_dominio_e_depois_url():
    chunks = [_chunk("https://a", domain="a.org"), _chunk("https://b")]

    fontes = fontes_web_a_partir_do_grounding(chunks, "q", lambda url: url)

    assert [f.titulo for f in fontes] == ["a.org", "https://b"]


# --- redirect do Google ---


def test_resolver_redirect_le_so_o_location_do_google(monkeypatch):
    chamadas = []

    def falso_get(url, **kwargs):
        chamadas.append((url, kwargs))
        return httpx.Response(302, headers={"location": "https://real.org/pagina"})

    monkeypatch.setattr(httpx, "get", falso_get)

    final = resolver_redirect("https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc")

    assert final == "https://real.org/pagina"
    assert chamadas[0][1]["follow_redirects"] is False


def test_resolver_redirect_nao_busca_pagina_de_terceiro(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("não deveria fazer request"))

    assert resolver_redirect("https://real.org/pagina") == "https://real.org/pagina"


def test_resolver_redirect_falha_de_rede_mantem_o_link(monkeypatch):
    def quebra(*a, **k):
        raise httpx.ConnectTimeout("lento")

    monkeypatch.setattr(httpx, "get", quebra)
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"

    assert resolver_redirect(url) == url


# --- ferramenta buscar_fontes_web ---


def test_ferramenta_e_async_para_rodar_dentro_do_event_loop_do_adk():
    """Regressão: sync, a ferramenta chamava `asyncio.run` dentro do loop já
    ativo do ADK e a busca nunca devolvia fontes."""
    ctx = _ctx(None)
    tool = {t.__name__: t for t in construir_tools_aluno(ctx)}["buscar_fontes_web"]

    assert asyncio.iscoroutinefunction(tool)


def test_ferramenta_acumula_fontes_no_ctx(fake_ai_provider):
    ctx = _ctx(fake_ai_provider)
    tools = {t.__name__: t for t in construir_tools_aluno(ctx)}

    resumo = asyncio.run(tools["buscar_fontes_web"]("fotossíntese"))

    assert resumo == "Resumo web sobre fotossíntese"
    assert [f.url for f in ctx.fontes_web] == ["https://example.org/a"]


def test_ferramenta_nao_repete_fonte_ja_vista(fake_ai_provider):
    ctx = _ctx(fake_ai_provider)
    tool = {t.__name__: t for t in construir_tools_aluno(ctx)}["buscar_fontes_web"]

    asyncio.run(tool("a"))
    asyncio.run(tool("b"))

    assert len(ctx.fontes_web) == 1


def test_ferramenta_falha_da_busca_nao_levanta_e_nao_deixa_fontes(fake_ai_provider):
    """RNF6: web search being down must not break the answer."""
    fake_ai_provider.falhar_pesquisar_web = True
    ctx = _ctx(fake_ai_provider)
    tool = {t.__name__: t for t in construir_tools_aluno(ctx)}["buscar_fontes_web"]

    resposta = asyncio.run(tool("qualquer coisa"))

    assert "indisponível" in resposta
    assert ctx.fontes_web == []


def test_ferramenta_limita_buscas_por_turno(fake_ai_provider):
    ctx = _ctx(fake_ai_provider)
    tool = {t.__name__: t for t in construir_tools_aluno(ctx)}["buscar_fontes_web"]

    for i in range(MAX_BUSCAS_WEB_POR_TURNO + 2):
        asyncio.run(tool(f"consulta {i}"))

    assert fake_ai_provider.pesquisar_web_calls == MAX_BUSCAS_WEB_POR_TURNO


def test_ferramenta_sem_resultados_orienta_a_responder_sem_fontes(fake_ai_provider):
    fake_ai_provider.resultado_pesquisa_web = ResultadoBuscaWeb(resumo="")
    ctx = _ctx(fake_ai_provider)
    tool = {t.__name__: t for t in construir_tools_aluno(ctx)}["buscar_fontes_web"]

    assert "sem fontes" in asyncio.run(tool("x"))
    assert ctx.fontes_web == []


# --- persistência no serviço ---


def test_servico_salva_fontes_na_resposta_ligadas_a_pergunta(fake_ai_provider):
    fake_ai_provider.consulta_web_do_agente = "fotossíntese"
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)
    ctx = _ctx(fake_ai_provider, conversa.id)

    chat_aluno_service.enviar_mensagem(
        conversa, "o que é fotossíntese?", conversa_repo, InMemoryModuloRepository(),
        fake_ai_provider, ctx, 20,
    )  # fmt: skip

    pergunta, resposta = conversa.mensagens
    assert pergunta.fontes is None
    assert resposta.fontes == [
        {
            "titulo": "Exemplo",
            "url": "https://example.org/a",
            "dominio": "example.org",
            "consulta": "fotossíntese",
        }
    ]
    assert resposta.pergunta_id == pergunta.id


def test_servico_sem_busca_nao_grava_fontes(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa()
    conversa_repo.add(conversa)

    chat_aluno_service.enviar_mensagem(
        conversa, "oi", conversa_repo, InMemoryModuloRepository(),
        fake_ai_provider, _ctx(fake_ai_provider, conversa.id), 20,
    )  # fmt: skip

    assert conversa.mensagens[-1].fontes is None


# --- histórico (sessão ADK não conhece as fontes) ---


def test_anexa_fontes_ao_historico_adk_pelo_texto_da_resposta():
    pergunta_id = uuid.uuid4()
    fontes = [{"titulo": "T", "url": "https://x.org", "dominio": None, "consulta": "q"}]
    mensagens = [
        Mensagem(papel=PAPEL_USUARIO, conteudo="pergunta", ordem=0),
        Mensagem(
            papel=PAPEL_ASSISTENTE, conteudo="resposta", ordem=1, fontes=fontes,
            pergunta_id=pergunta_id,
        ),  # fmt: skip
    ]
    agora = datetime.now(UTC)
    historico = [
        MensagemHistorico(uuid.uuid4(), "user", "pergunta", None, agora),
        MensagemHistorico(uuid.uuid4(), "assistant", "resposta", None, agora),
        MensagemHistorico(uuid.uuid4(), "assistant", "outra sem fonte", None, agora),
    ]

    resultado = chat_aluno_service.anexar_fontes_ao_historico(historico, mensagens)

    assert resultado[0].fontes is None
    assert resultado[1].fontes == fontes
    assert resultado[1].pergunta_id == pergunta_id
    assert resultado[2].fontes is None
