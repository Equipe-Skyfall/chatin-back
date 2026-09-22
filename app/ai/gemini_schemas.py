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

RESUMO_ESTUDO_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "visao_geral": {"type": "STRING"},
        "conceitos_chave": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "termo": {"type": "STRING"},
                    "explicacao": {"type": "STRING"},
                },
                "required": ["termo", "explicacao"],
            },
        },
        "pontos_importantes": {"type": "ARRAY", "items": {"type": "STRING"}},
        "exemplos": {"type": "ARRAY", "items": {"type": "STRING"}},
        "duvidas_do_aluno": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "pergunta": {"type": "STRING"},
                    "resposta": {"type": "STRING"},
                },
                "required": ["pergunta", "resposta"],
            },
        },
        "revisao_rapida": {"type": "ARRAY", "items": {"type": "STRING"}},
        "fontes": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "visao_geral",
        "conceitos_chave",
        "pontos_importantes",
        "exemplos",
        "duvidas_do_aluno",
        "revisao_rapida",
        "fontes",
    ],
}
