from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import EstadoProgresso


class ProgressoModuloOut(BaseModel):
    modulo_id: UUID
    titulo: str
    estado: EstadoProgresso
    melhor_pontuacao: float | None
    tentativas_count: int


class ProgressoTemaOut(BaseModel):
    tema_id: UUID
    titulo: str
    estado: EstadoProgresso
    percentual_completo: float
    modulos: list[ProgressoModuloOut]


class ProgressoMateriaOut(BaseModel):
    materia_id: UUID
    nome: str
    estado: EstadoProgresso
    percentual_completo: float
    temas: list[ProgressoTemaOut]


class ProgressoOut(BaseModel):
    materias: list[ProgressoMateriaOut]
