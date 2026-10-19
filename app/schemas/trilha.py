from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import EstadoProgresso


class TrilhaModuloOut(BaseModel):
    id: UUID
    titulo: str
    ordem: int
    estado: EstadoProgresso


class TrilhaTemaOut(BaseModel):
    id: UUID
    titulo: str
    ordem: int
    estado: EstadoProgresso
    modulos: list[TrilhaModuloOut]


class TrilhaMateriaOut(BaseModel):
    id: UUID
    nome: str
    temas: list[TrilhaTemaOut]


class TrilhaOut(BaseModel):
    materias: list[TrilhaMateriaOut]
