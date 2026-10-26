"""Classification of failures coming from the AI provider.

Kept free of provider imports (no `google.genai`, no `httpx`) so the domain
exceptions can use it without a dependency cycle: the exception inspects the
original error it wraps by duck typing instead of by class.
"""

from enum import StrEnum

HTTP_TIMEOUT = (408, 504)
HTTP_LIMITE = 429


class TipoFalhaIA(StrEnum):
    TIMEOUT = "timeout"  # the provider took too long (or never answered)
    LIMITE = "limite"  # quota / rate limit - worth retrying shortly
    INDISPONIVEL = "indisponivel"  # 5xx, dropped connection, empty reply
    PERMANENTE = "permanente"  # 4xx: a retry cannot succeed (bad key, bad request)


def classificar_falha(causa: BaseException | None) -> TipoFalhaIA:
    """`causa` is the original error the provider wrapped (`raise ... from exc`),
    or `None` when the failure was detected without one (e.g. an empty reply)."""
    if causa is None:
        return TipoFalhaIA.INDISPONIVEL

    if isinstance(causa, TimeoutError) or any("Timeout" in c.__name__ for c in type(causa).__mro__):
        return TipoFalhaIA.TIMEOUT

    codigo = getattr(causa, "code", None)
    if isinstance(codigo, int):
        if codigo in HTTP_TIMEOUT:
            return TipoFalhaIA.TIMEOUT
        if codigo == HTTP_LIMITE:
            return TipoFalhaIA.LIMITE
        if 400 <= codigo < 500:
            return TipoFalhaIA.PERMANENTE
    return TipoFalhaIA.INDISPONIVEL
