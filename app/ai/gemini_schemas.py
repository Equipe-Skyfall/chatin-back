"""Gemini structured-output schemas (the `response_schema` config passed to
`generate_content`) - distinct from `prompts.py` (text prompt templates) and
from `schemas.py` (provider-agnostic result DTOs every `AIProvider` returns).
This one is Gemini's own schema dialect (uppercase type names, etc.) and has
no meaning for another concrete provider.
"""

from typing import Any

QUESTIONARIO_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "enunciado": {"type": "STRING"},
            "alternativas": {
                "type": "ARRAY",
                # Strings, not ints: matches google-genai's Schema type (min_items/
                # max_items are `str`) - response_schema tolerated ints in testing,
                # but this is the actually-correct type, so keep it consistent.
                "minItems": "5",
                "maxItems": "5",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "letra": {"type": "STRING", "enum": ["A", "B", "C", "D", "E"]},
                        "texto": {"type": "STRING"},
                    },
                    "required": ["letra", "texto"],
                },
            },
            "resposta_correta": {"type": "STRING", "enum": ["A", "B", "C", "D", "E"]},
            "explicacao": {"type": "STRING"},
        },
        "required": ["enunciado", "alternativas", "resposta_correta", "explicacao"],
    },
}

PLANO_MODULOS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "minItems": "1",
    "maxItems": "5",
    "items": {
        "type": "OBJECT",
        "properties": {
            "titulo": {"type": "STRING"},
            "descricao": {"type": "STRING"},
        },
        "required": ["titulo", "descricao"],
    },
}
