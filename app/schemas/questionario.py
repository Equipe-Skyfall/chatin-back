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
    """Describes the tentativa returned, which is always the quiz the caller
    asked for: an open tentativa of the same scope and kind is resumed (same
    questions), and any other open one is discarded first (see
    `grading_service.iniciar_tentativa_com_pool`). `pratica`/`questionario_id`/
    `tema_id` say which quiz it is."""

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


MAX_QUESTOES_POR_QUESTIONARIO = 50


class QuestaoCreate(BaseModel):
    """A questão written by hand: unlike `QuestaoUpdate` nothing is optional,
    since there is no generated version to fall back on."""

    enunciado: str = Field(..., min_length=1)
    alternativas: list[AlternativaOut] = Field(..., min_length=5, max_length=5)
    explicacao: str | None = None
    resposta_correta: Letra

    @field_validator("alternativas")
    @classmethod
    def _letras_devem_ser_a_a_e(cls, v: list[AlternativaOut]) -> list[AlternativaOut]:
        if {alt.letra for alt in v} != _LETRAS_VALIDAS:
            raise ValueError(
                "alternativas devem conter exatamente as letras A, B, C, D, E, uma vez cada."
            )
        return v


class QuestionarioCreate(BaseModel):
    """A whole quiz in one request. The order of `questoes` is the order kept."""

    questoes: list[QuestaoCreate] = Field(
        ..., min_length=1, max_length=MAX_QUESTOES_POR_QUESTIONARIO
    )
