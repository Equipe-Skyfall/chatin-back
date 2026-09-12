"""Unit tests for `AdkProvider` (Fases 1-2 of the ADK migration): the
`gerar_questionario`/`planejar_modulos` output-schema methods and the
`gerar_conteudo_modulo`/`buscar_fontes` plain-text/grounded methods, mocked at
the `_run_single_turn`/`_run_single_turn_full` seam so no real ADK
`Runner`/Gemini call happens. The three not-yet-migrated methods (needing a
persistent, multi-turn `SessionService` - Fase 3) are covered by proving they
delegate to the internal `GeminiProvider` instance untouched.
"""

from unittest.mock import patch

import pytest

from app.ai.adk_provider import AdkProvider
from app.ai.schemas import ConteudoGerado, FonteEncontrada, PlanoModulos, QuestionarioGerado
from app.config import Settings
from app.core.exceptions import ProvedorIAIndisponivelException


def _settings() -> Settings:
    return Settings(
        SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
        JWT_SECRET="test-secret",
        GEMINI_API_KEY="fake-key",
        AI_PROVIDER="adk",
    )


@pytest.fixture
def provider() -> AdkProvider:
    return AdkProvider(_settings())


def _mock_run_single_turn(raw: str):
    return patch.object(AdkProvider, "_run_single_turn", staticmethod(lambda agent, prompt: raw))


def _mock_run_single_turn_full(texto: str, grounding=None):
    return patch.object(
        AdkProvider,
        "_run_single_turn_full",
        staticmethod(lambda agent, prompt: (texto, grounding)),
    )


def test_gerar_questionario_mapeia_schema_para_dataclass(provider):
    raw = """
    {"questoes": [
        {"enunciado": "Quanto é 2+2?",
         "alternativas": [
             {"letra": "A", "texto": "3"},
             {"letra": "B", "texto": "4"},
             {"letra": "C", "texto": "5"},
             {"letra": "D", "texto": "6"},
             {"letra": "E", "texto": "7"}
         ],
         "resposta_correta": "B",
         "explicacao": "2+2 é igual a 4."}
    ]}
    """
    with _mock_run_single_turn(raw):
        resultado = provider.gerar_questionario("conteúdo", None, 1)

    assert isinstance(resultado, QuestionarioGerado)
    assert resultado.modelo == provider._settings.GEMINI_MODEL_QUESTIONARIO
    assert len(resultado.questoes) == 1
    questao = resultado.questoes[0]
    assert questao.enunciado == "Quanto é 2+2?"
    assert questao.resposta_correta == "B"
    assert len(questao.alternativas) == 5


def test_gerar_questionario_com_quantidade_errada_levanta_excecao(provider):
    raw = """{"questoes": [
        {"enunciado": "A",
         "alternativas": [
             {"letra": "A", "texto": "1"},
             {"letra": "B", "texto": "2"},
             {"letra": "C", "texto": "3"},
             {"letra": "D", "texto": "4"},
             {"letra": "E", "texto": "5"}
         ],
         "resposta_correta": "A",
         "explicacao": "x"}
    ]}"""
    with _mock_run_single_turn(raw):
        with pytest.raises(ProvedorIAIndisponivelException):
            provider.gerar_questionario("conteúdo", None, 2)


def test_gerar_questionario_com_json_invalido_levanta_excecao(provider):
    with _mock_run_single_turn("isso não é JSON"):
        with pytest.raises(ProvedorIAIndisponivelException):
            provider.gerar_questionario("conteúdo", None, 1)


def test_planejar_modulos_mapeia_schema_e_respeita_max_modulos(provider):
    raw = """{"modulos": [
        {"titulo": "Módulo 1", "descricao": "Foco 1"},
        {"titulo": "Módulo 2", "descricao": "Foco 2"},
        {"titulo": "Módulo 3", "descricao": "Foco 3"}
    ]}"""
    with _mock_run_single_turn(raw):
        resultado = provider.planejar_modulos("Tema", None, ["fonte"], max_modulos=2)

    assert isinstance(resultado, PlanoModulos)
    assert len(resultado.modulos) == 2
    assert resultado.modulos[0].titulo == "Módulo 1"


def test_planejar_modulos_com_json_invalido_levanta_excecao(provider):
    with _mock_run_single_turn("não é JSON"):
        with pytest.raises(ProvedorIAIndisponivelException):
            provider.planejar_modulos("Tema", None, ["fonte"], max_modulos=3)


def test_gerar_conteudo_modulo_retorna_texto_da_ia(provider):
    with _mock_run_single_turn("# Conteúdo\n\nTexto didático gerado."):
        resultado = provider.gerar_conteudo_modulo("Tema", "Módulo", None, ["fonte"])

    assert isinstance(resultado, ConteudoGerado)
    assert resultado.conteudo == "# Conteúdo\n\nTexto didático gerado."
    assert resultado.modelo == provider._settings.GEMINI_MODEL_CONTEUDO


def test_gerar_conteudo_modulo_vazio_levanta_excecao(provider):
    with _mock_run_single_turn("   "):
        with pytest.raises(ProvedorIAIndisponivelException):
            provider.gerar_conteudo_modulo("Tema", "Módulo", None, ["fonte"])


def test_buscar_fontes_com_grounding_mapeia_chunks(provider):
    class _Web:
        def __init__(self, title, uri):
            self.title = title
            self.uri = uri

    class _Chunk:
        def __init__(self, web):
            self.web = web

    class _Grounding:
        def __init__(self, chunks):
            self.grounding_chunks = chunks

    grounding = _Grounding([_Chunk(_Web("Fonte A", "https://a.example"))])
    with _mock_run_single_turn_full("texto sintetizado", grounding):
        fontes = provider.buscar_fontes("Tema", None)

    assert len(fontes) == 1
    assert isinstance(fontes[0], FonteEncontrada)
    assert fontes[0].titulo == "Fonte A"
    assert fontes[0].origem == "https://a.example"
    assert fontes[0].conteudo == "texto sintetizado"


def test_buscar_fontes_sem_grounding_usa_fallback(provider):
    with _mock_run_single_turn_full("texto sintetizado", None):
        fontes = provider.buscar_fontes("Tema", None)

    assert len(fontes) == 1
    assert fontes[0].titulo == "Busca automática: Tema"
    assert fontes[0].origem is None
    assert fontes[0].conteudo == "texto sintetizado"


@pytest.mark.parametrize(
    "metodo,args",
    [
        ("responder_pergunta_aluno", ([], "pergunta")),
        ("resumir_conversa", ([],)),
    ],
)
def test_metodos_nao_migrados_delegam_para_gemini_provider(provider, metodo, args):
    with patch.object(provider._gemini, metodo, return_value="ok") as mock_metodo:
        resultado = getattr(provider, metodo)(*args)

    mock_metodo.assert_called_once()
    assert resultado == "ok"


def test_conversar_com_ferramentas_delega_para_gemini_provider(provider):
    with patch.object(
        provider._gemini, "conversar_com_ferramentas", return_value="ok"
    ) as mock_metodo:
        resultado = provider.conversar_com_ferramentas([], [])

    mock_metodo.assert_called_once()
    assert resultado == "ok"


def test_questionario_schema_invalido_por_pydantic_e_reportado(provider):
    """5 alternativas é imposto pelo próprio `Field(min_length=5, max_length=5)`
    do `QuestionarioSchema` - um retorno com 4 alternativas já falha a
    validação do Pydantic antes mesmo de checar a quantidade de questões."""
    raw = """{"questoes": [
        {"enunciado": "A",
         "alternativas": [
             {"letra": "A", "texto": "1"},
             {"letra": "B", "texto": "2"},
             {"letra": "C", "texto": "3"},
             {"letra": "D", "texto": "4"}
         ],
         "resposta_correta": "A",
         "explicacao": "x"}
    ]}"""
    with _mock_run_single_turn(raw):
        with pytest.raises(ProvedorIAIndisponivelException):
            provider.gerar_questionario("conteúdo", None, 1)
