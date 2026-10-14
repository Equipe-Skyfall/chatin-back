import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AgenteLimiteExcedidoException, ProvedorIAIndisponivelException
from app.core.falha_ia import TipoFalhaIA, classificar_falha


def _api_error(codigo: int) -> genai_errors.APIError:
    return genai_errors.APIError(codigo, {"error": {"message": "x", "status": "X"}})


def _falha_com_causa(causa: BaseException | None) -> ProvedorIAIndisponivelException:
    exc = ProvedorIAIndisponivelException("falha tecnica")
    exc.__cause__ = causa
    return exc


@pytest.mark.parametrize(
    ("causa", "esperado"),
    [
        (None, TipoFalhaIA.INDISPONIVEL),
        (httpx.ReadTimeout("lento"), TipoFalhaIA.TIMEOUT),
        (TimeoutError(), TipoFalhaIA.TIMEOUT),
        (_api_error(504), TipoFalhaIA.TIMEOUT),
        (_api_error(408), TipoFalhaIA.TIMEOUT),
        (_api_error(429), TipoFalhaIA.LIMITE),
        (_api_error(503), TipoFalhaIA.INDISPONIVEL),
        (_api_error(500), TipoFalhaIA.INDISPONIVEL),
        (_api_error(400), TipoFalhaIA.PERMANENTE),
        (_api_error(403), TipoFalhaIA.PERMANENTE),
        (httpx.ConnectError("sem rede"), TipoFalhaIA.INDISPONIVEL),
        (RuntimeError("qualquer coisa"), TipoFalhaIA.INDISPONIVEL),
    ],
)
def test_classificar_falha(causa, esperado):
    assert classificar_falha(causa) is esperado


def test_timeout_vira_504_com_codigo_proprio():
    exc = _falha_com_causa(httpx.ReadTimeout("lento"))

    assert exc.status_code == 504
    assert exc.code == "ia_timeout"


@pytest.mark.parametrize("causa", [None, _api_error(503), _api_error(429), _api_error(403)])
def test_demais_falhas_viram_503_ia_indisponivel(causa):
    exc = _falha_com_causa(causa)

    assert exc.status_code == 503
    assert exc.code == "ia_indisponivel"


def test_detalhe_e_amigavel_e_nao_vaza_o_motivo_tecnico():
    exc = _falha_com_causa(_api_error(503))

    assert "falha tecnica" not in exc.detail
    assert "indisponível" in exc.detail
    assert exc.motivo == "falha tecnica"
    assert str(exc) == "falha tecnica"  # still what the logs show


def _app_com_rota(excecao: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/falha")
    def falha():
        raise excecao

    return TestClient(app, raise_server_exceptions=False)


def test_resposta_http_traz_o_codigo_para_o_frontend():
    resposta = _app_com_rota(_falha_com_causa(_api_error(503))).get("/falha")

    assert resposta.status_code == 503
    assert resposta.json()["code"] == "ia_indisponivel"
    assert "indisponível" in resposta.json()["detail"]


def test_resposta_http_de_timeout_e_504():
    resposta = _app_com_rota(_falha_com_causa(httpx.ReadTimeout("lento"))).get("/falha")

    assert resposta.status_code == 504
    assert resposta.json()["code"] == "ia_timeout"


def test_erros_comuns_continuam_sem_codigo():
    resposta = _app_com_rota(AgenteLimiteExcedidoException()).get("/falha")

    assert "code" not in resposta.json()
