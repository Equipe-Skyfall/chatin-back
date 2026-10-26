"""Resilience helpers for calls to the AI provider (US-14)."""

from functools import wraps

from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.ai import consumo
from app.ai.disponibilidade import status_ia
from app.config import Settings
from app.core.exceptions import ProvedorIAIndisponivelException
from app.core.falha_ia import TipoFalhaIA


def opcoes_http(settings: Settings) -> types.HttpOptions:
    """Request options shared by every Gemini client/agent. `HttpOptions.timeout`
    is expressed in milliseconds."""
    return types.HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000))


# Only these are worth another attempt: the provider may well answer a moment
# later. A timeout already made the user wait `GEMINI_TIMEOUT_SECONDS`, and a
# permanent error (bad key, rejected request) fails identically every time.
_TIPOS_COM_RETRY = {TipoFalhaIA.LIMITE, TipoFalhaIA.INDISPONIVEL}


def _vale_repetir(exc: BaseException) -> bool:
    return isinstance(exc, ProvedorIAIndisponivelException) and exc.tipo in _TIPOS_COM_RETRY


def retry_transiente(tentativas: int = 3, espera_max: int = 8):
    """Retry with exponential backoff, only for failures `_vale_repetir` accepts.
    The final outcome of each call (after the retries) is reported to
    `status_ia`, which backs `GET /ia/status`. Each attempt is also recorded as
    its own usage row (RNF7, `app/ai/consumo.py`) - every retry is a billed call."""
    politica = retry(
        stop=stop_after_attempt(tentativas),
        wait=wait_exponential(multiplier=1, min=1, max=espera_max),
        retry=retry_if_exception(_vale_repetir),
        reraise=True,
    )

    def decorador(funcao):
        @wraps(funcao)
        def tentativa(*args, **kwargs):
            with consumo.medir(funcao.__name__):
                return funcao(*args, **kwargs)

        com_retry = politica(tentativa)

        @wraps(funcao)
        def envolvida(*args, **kwargs):
            try:
                resultado = com_retry(*args, **kwargs)
            except ProvedorIAIndisponivelException:
                status_ia.registrar_falha()
                raise
            status_ia.registrar_sucesso()
            return resultado

        return envolvida

    return decorador
