from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import EstadoProgresso


class ProgressoModuloOut(BaseModel):
    modulo_id: UUID
    titulo: str
    estado: EstadoProgresso
    melhor_pontuacao: float | None
    tentativas_count: int


NivelDesempenho = Literal["baixo", "medio", "alto"]


class DesempenhoTemaOut(BaseModel):
    """Performance in one tema, from every answer in the student's completed
    quizzes. `nivel` stays "medio" until there are enough answers to trust."""

    nivel: NivelDesempenho
    taxa_acerto: float
    total_respostas: int


class ProgressoTemaOut(BaseModel):
    tema_id: UUID
    titulo: str
    estado: EstadoProgresso
    percentual_completo: float
    desempenho: DesempenhoTemaOut
    modulos: list[ProgressoModuloOut]


class ProgressoMateriaOut(BaseModel):
    materia_id: UUID
    nome: str
    estado: EstadoProgresso
    percentual_completo: float
    xp: int
    temas: list[ProgressoTemaOut]


class ProgressoOut(BaseModel):
    materias: list[ProgressoMateriaOut]
