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
    resposta_escolhida: Letra
    resposta_correta: Letra
    correta: bool
    explicacao: str | None


class TentativaResultadoOut(BaseModel):
    id: UUID
    questionario_id: UUID
    pontuacao: float
    total_questoes: int
    total_corretas: int
    resultados: list[RespostaResultadoOut]
