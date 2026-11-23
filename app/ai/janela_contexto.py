"""Keeps the chat's AI cost flat as a conversation grows.

The ADK runner replays the whole stored session on every turn, so the message
window the services apply (`MEMORIA_JANELA_MENSAGENS`) never reaches it - it
only ever sends the last message. A `before_model_callback` trims what is about
to go to the model instead: the last `janela` text messages, started at a user
message so the model never sees a reply without its question, and never in the
middle of a tool call (a function call and its response stay together because
only text messages are counted and the cut lands on a user text message).
"""

from collections.abc import Callable, Sequence
from typing import Any


def _eh_mensagem_de_texto(content: Any) -> bool:
    partes = getattr(content, "parts", None) or []
    if any(
        getattr(p, "function_call", None) or getattr(p, "function_response", None) for p in partes
    ):
        return False
    return any(getattr(p, "text", None) for p in partes)


def recortar(contents: Sequence[Any], janela: int) -> list[Any]:
    """The last `janela` text messages of `contents` and everything after the
    cut; `contents` unchanged when it already fits."""
    textos = [i for i, c in enumerate(contents) if _eh_mensagem_de_texto(c)]
    if janela < 1 or len(textos) <= janela:
        return list(contents)
    corte = textos[-janela]
    # Start on a user message: a window that opens on a model reply is invalid
    # for Gemini and loses the question it answers.
    for i in textos:
        if i >= corte and getattr(contents[i], "role", None) == "user":
            return list(contents[i:])
    return list(contents[textos[-1] :])


def criar_callback(janela: int) -> Callable[[Any, Any], None]:
    """An ADK `before_model_callback` that trims the request to `janela` text
    messages. Returning `None` lets the (trimmed) request go on to the model."""

    def antes_do_modelo(callback_context: Any, llm_request: Any) -> None:
        llm_request.contents[:] = recortar(llm_request.contents, janela)
        return None

    return antes_do_modelo
