"""Unit tests for `AdkProvider` (Fase 1 of the ADK migration): the
`gerar_questionario`/`planejar_modulos` output-schema methods, mocked at the
`_run_single_turn` seam so no real ADK `Runner`/Gemini call happens. The five
not-yet-migrated methods are covered by proving they delegate to the internal
`GeminiProvider` instance untouched.
"""

from unittest.mock import patch

import pytest

from app.ai.adk_provider import AdkProvider
from app.ai.schemas import PlanoModulos, QuestionarioGerado
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


@pytest.mark.parametrize(
    "metodo,args",
    [
        ("buscar_fontes", ("Tema", None)),
        ("gerar_conteudo_modulo", ("Tema", "Módulo", None, ["fonte"])),
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
