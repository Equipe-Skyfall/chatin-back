from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.questionario import Letra


class RespostaInput(BaseModel):
    questao_id: UUID
    resposta_escolhida: Letra


class ResponderRequest(BaseModel):
    respostas: list[RespostaInput] = Field(..., min_length=1)


class RespostaResultadoOut(BaseModel):
    questao_id: UUID
    enunciado: str
    resposta_escolhida: Letra
    resposta_correta: Letra
    correta: bool
    explicacao: str | None


class TentativaResultadoOut(BaseModel):
    id: UUID
    questionario_id: UUID | None
    tema_id: UUID | None
    pontuacao: float
    total_questoes: int
    total_corretas: int
    aprovado: bool
    feedback: str | None = None
    resultados: list[RespostaResultadoOut]


class TentativaHistoricoOut(BaseModel):
    id: UUID
    modulo_id: UUID | None
    modulo_titulo: str | None
    tema_id: UUID | None
    tema_titulo: str | None
    status: str
    pontuacao: float | None
    total_questoes: int
    total_corretas: int | None
    created_at: datetime
