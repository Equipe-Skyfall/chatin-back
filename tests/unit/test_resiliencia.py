import httpx
import pytest
from google.genai import errors as genai_errors

from app.ai import resiliencia
from app.config import Settings
from app.core.exceptions import AgenteLimiteExcedidoException, ProvedorIAIndisponivelException


def _settings(**extra) -> Settings:
    return Settings(
        SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
        JWT_SECRET="test-secret",
        GEMINI_API_KEY="fake-key",
        **extra,
    )


def test_timeout_http_vem_da_config_em_milissegundos():
    opcoes = resiliencia.opcoes_http(_settings(GEMINI_TIMEOUT_SECONDS=12.5))

    assert opcoes.timeout == 12500


def test_timeout_padrao_e_de_60_segundos():
    assert resiliencia.opcoes_http(_settings()).timeout == 60000


def _api_error(codigo: int) -> genai_errors.APIError:
    return genai_errors.APIError(codigo, {"error": {"message": "x", "status": "X"}})


def _falha_com_causa(causa: BaseException | None) -> ProvedorIAIndisponivelException:
    exc = ProvedorIAIndisponivelException("falha tecnica")
    exc.__cause__ = causa
    return exc


@pytest.mark.parametrize(
    ("causa", "repete"),
    [
        (None, True),
        (_api_error(503), True),
        (_api_error(429), True),
        (httpx.ReadTimeout("lento"), False),
        (_api_error(403), False),
        (_api_error(400), False),
    ],
)
def test_so_repete_falhas_transitorias(causa, repete):
    assert resiliencia._vale_repetir(_falha_com_causa(causa)) is repete


def test_nao_repete_o_que_nao_e_falha_do_provedor():
    assert resiliencia._vale_repetir(AgenteLimiteExcedidoException()) is False
    assert resiliencia._vale_repetir(ValueError()) is False


def test_retry_para_na_primeira_tentativa_quando_a_falha_e_permanente():
    chamadas = 0

    @resiliencia.retry_transiente(tentativas=3, espera_max=1)
    def chamar():
        nonlocal chamadas
        chamadas += 1
        raise _falha_com_causa(_api_error(403))

    with pytest.raises(ProvedorIAIndisponivelException):
        chamar()

    assert chamadas == 1


def test_retry_tenta_de_novo_quando_a_falha_e_transitoria():
    chamadas = 0

    @resiliencia.retry_transiente(tentativas=3, espera_max=1)
    def chamar():
        nonlocal chamadas
        chamadas += 1
        if chamadas < 2:
            raise _falha_com_causa(_api_error(503))
        return "ok"

    assert chamar() == "ok"
    assert chamadas == 2
