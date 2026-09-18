from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Letra = Literal["A", "B", "C", "D", "E"]
_LETRAS_VALIDAS = frozenset("ABCDE")


class AlternativaOut(BaseModel):
    letra: Letra
    texto: str


class QuestaoOut(BaseModel):
    """Client-facing shape - structurally incapable of carrying the gabarito:
    there is no `resposta_correta` field here at all.
    """

    id: UUID
    ordem: int
    enunciado: str
    alternativas: list[AlternativaOut]


class TentativaIniciarOut(BaseModel):
    """Always describes the tentativa actually returned - which, because of
    the 1-open-questionário-at-a-time limit, may not be the mode/scope the
    caller just asked for (e.g. `POST .../tentativas` can hand back an open
    `pratica` tentativa the student never finished). `pratica`/
    `questionario_id`/`tema_id` let the client render this honestly instead
    of assuming it always matches the endpoint it called."""

    tentativa_id: UUID
    questoes: list[QuestaoOut]
    pratica: bool
    questionario_id: UUID | None = None
    tema_id: UUID | None = None


class QuestaoAdminOut(BaseModel):
    """Admin-only shape for reviewing/editing a stored questão - unlike
    `QuestaoOut`, this one does carry `resposta_correta`. Never returned from
    a student-facing route."""

    id: UUID
    ordem: int
    enunciado: str
    alternativas: list[AlternativaOut]
    explicacao: str | None
    resposta_correta: Letra


class QuestaoUpdate(BaseModel):
    """Partial edit of an already-generated questão - a manual correction,
    not a regeneration. Every field is optional; only what's provided changes.
    """

    enunciado: str | None = Field(None, min_length=1)
    alternativas: list[AlternativaOut] | None = Field(None, min_length=5, max_length=5)
    explicacao: str | None = None
    resposta_correta: Letra | None = None

    @field_validator("alternativas")
    @classmethod
    def _letras_devem_ser_a_a_e(cls, v: list[AlternativaOut] | None) -> list[AlternativaOut] | None:
        if v is not None and {alt.letra for alt in v} != _LETRAS_VALIDAS:
            raise ValueError(
                "alternativas devem conter exatamente as letras A, B, C, D, E, uma vez cada."
            )
        return v
