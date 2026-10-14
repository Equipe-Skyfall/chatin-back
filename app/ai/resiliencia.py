"""Resilience helpers for calls to the AI provider (US-14)."""

from google.genai import types

from app.config import Settings


def opcoes_http(settings: Settings) -> types.HttpOptions:
    """Request options shared by every Gemini client/agent. `HttpOptions.timeout`
    is expressed in milliseconds."""
    return types.HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000))
