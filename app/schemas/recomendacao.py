from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

MotivoRecomendacao = Literal["nao_estudado", "baixo_desempenho", "revisao_espacada"]


class RecomendacaoOut(BaseModel):
    modulo_id: UUID
    modulo_titulo: str
    tema_id: UUID
    tema_titulo: str
    materia_id: UUID
    materia_nome: str
    motivo: MotivoRecomendacao
    justificativa: str
    prioridade: float
    ultimo_estudo: datetime | None
    dias_desde_ultimo_estudo: int | None
    taxa_acerto_tema: float | None


class RecomendacaoResposta(BaseModel):
    """`recomendacao` is null when the student has no módulo available yet."""

    recomendacao: RecomendacaoOut | None
