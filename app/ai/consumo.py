"""Usage accounting for AI provider calls (RNF7).

Every call is measured with `medir(operacao)` and reported to a *recorder*.
The whole thing is best-effort by design: the AI is already an optional
dependency of the app (RNF6), and the bookkeeping must not become a second one.
Nothing in here may raise into the caller - a failed insert, a missing table
(migration not applied yet) or a provider response without usage data only
costs a log line and a row, never the request.
"""

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.core.falha_ia import TipoFalhaIA

logger = logging.getLogger(__name__)

_usuario: ContextVar[str | None] = ContextVar("consumo_ia_usuario", default=None)
_medicao: ContextVar["Medicao | None"] = ContextVar("consumo_ia_medicao", default=None)


@dataclass
class Medicao:
    """What one provider call used. Filled in while the call runs."""

    operacao: str
    modelo: str | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    chamadas_modelo: int = 0
    inicio: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class RegistroConsumo:
    user_id: str | None
    operacao: str
    modelo: str | None
    sucesso: bool
    tipo_falha: str | None
    tokens_entrada: int | None
    tokens_saida: int | None
    chamadas_modelo: int
    duracao_ms: int


def definir_usuario(user_id: str | None) -> None:
    """Attributes the AI calls made while handling this request to `user_id`."""
    _usuario.set(user_id)


def acumular(uso: Any, modelo: str | None = None) -> None:
    """Adds one model response's usage (`usage_metadata` of a Gemini response or
    ADK event) to the call being measured. No-op outside `medir`, and tolerant
    of a missing/odd `uso`."""
    medicao = _medicao.get()
    if medicao is None or uso is None:
        return
    try:
        medicao.chamadas_modelo += 1
        if modelo and not medicao.modelo:
            medicao.modelo = str(modelo)[:80]
        entrada = getattr(uso, "prompt_token_count", None)
        saida = getattr(uso, "candidates_token_count", None)
        if isinstance(entrada, int):
            medicao.tokens_entrada = (medicao.tokens_entrada or 0) + entrada
        if isinstance(saida, int):
            medicao.tokens_saida = (medicao.tokens_saida or 0) + saida
    except Exception:  # noqa: BLE001 - accounting never breaks the call
        logger.debug("não foi possível ler o uso de tokens", exc_info=True)


def _gravar_no_banco(registro: RegistroConsumo) -> None:
    # Imported here so importing the AI layer never requires DB settings.
    from app.db.session import nova_sessao
    from app.models.ia_consumo import IaConsumo

    sessao = nova_sessao()
    try:
        sessao.add(IaConsumo(**registro.__dict__))
        sessao.commit()
    finally:
        sessao.close()


_gravador: Callable[[RegistroConsumo], None] = _gravar_no_banco


def definir_gravador(gravador: Callable[[RegistroConsumo], None] | None) -> None:
    """Swaps where records go (tests use an in-memory list); `None` restores the
    database recorder."""
    global _gravador
    _gravador = gravador or _gravar_no_banco


def registrar(registro: RegistroConsumo) -> None:
    try:
        _gravador(registro)
    except Exception:  # noqa: BLE001 - RNF6: accounting is optional
        logger.warning("falha ao registrar o consumo de IA (%s)", registro.operacao, exc_info=True)


def _tipo_da_falha(exc: BaseException) -> str:
    tipo = getattr(exc, "tipo", None)
    return str(tipo) if tipo is not None else TipoFalhaIA.INDISPONIVEL.value


@contextmanager
def medir(operacao: str) -> Iterator[Medicao]:
    """Measures one provider call and records it when the block ends, whether it
    succeeded or raised. Exceptions from the block propagate untouched."""
    medicao = Medicao(operacao=operacao)
    token = _medicao.set(medicao)
    sucesso, tipo_falha = True, None
    try:
        yield medicao
    except BaseException as exc:
        sucesso, tipo_falha = False, _tipo_da_falha(exc)
        raise
    finally:
        _medicao.reset(token)
        registrar(
            RegistroConsumo(
                user_id=_usuario.get(),
                operacao=operacao,
                modelo=medicao.modelo,
                sucesso=sucesso,
                tipo_falha=tipo_falha,
                tokens_entrada=medicao.tokens_entrada,
                tokens_saida=medicao.tokens_saida,
                chamadas_modelo=max(medicao.chamadas_modelo, 1),
                duracao_ms=int((time.monotonic() - medicao.inicio) * 1000),
            )
        )
