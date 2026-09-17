"""Pydantic `output_schema` models used only at the ADK boundary (`LlmAgent`
output validation) - distinct from `app/ai/schemas.py` (provider-agnostic
dataclasses every `AIProvider` returns) and from the now-retired
`gemini_schemas.py` (Gemini's own uppercase-typed JSON schema dialect, still
used by the legacy `GeminiProvider`). `AdkProvider` maps a validated instance
of one of these back into the matching dataclass from `app/ai/schemas.py` at
the edge - callers never see these types.
"""

from typing import Literal

from pydantic import BaseModel, Field

Letra = Literal["A", "B", "C", "D", "E"]


class AlternativaSchema(BaseModel):
    letra: Letra
    texto: str


class QuestaoSchema(BaseModel):
    enunciado: str
    alternativas: list[AlternativaSchema] = Field(min_length=5, max_length=5)
    resposta_correta: Letra
    explicacao: str


class QuestionarioSchema(BaseModel):
    questoes: list[QuestaoSchema]


class ModuloPlanejadoSchema(BaseModel):
    titulo: str
    descricao: str


class PlanoModulosSchema(BaseModel):
    modulos: list[ModuloPlanejadoSchema] = Field(min_length=1)
