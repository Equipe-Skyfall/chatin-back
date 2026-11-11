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
    """One ranking line. Only the apelido identifies a student - never the
    real name or the user id; `eu` marks the caller's own line."""

    posicao: int
    apelido: str
    xp: int
    eu: bool = False


class RankingOut(BaseModel):
    entradas: list[RankingEntradaOut]
    # The caller's own line, also when they fall outside `entradas` (`None`
    # while they have no XP in this ranking).
    minha_posicao: RankingEntradaOut | None = None
