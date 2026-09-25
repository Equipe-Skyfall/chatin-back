from uuid import UUID

from pydantic import BaseModel


class XpPorMateriaOut(BaseModel):
    materia_id: UUID
    materia_nome: str
    xp: int


class MeuXpOut(BaseModel):
    xp_total: int
    nivel: int
    xp_proximo_nivel: int
    xp_faltando_proximo_nivel: int
    por_materia: list[XpPorMateriaOut]


class RankingEntradaOut(BaseModel):
    posicao: int
    user_id: str
    nome: str | None
    xp: int


class RankingOut(BaseModel):
    entradas: list[RankingEntradaOut]
