from uuid import UUID

from pydantic import BaseModel


class XpPorMateriaOut(BaseModel):
    materia_id: UUID
    materia_nome: str
    xp: int


class MeuXpOut(BaseModel):
    xp_total: int
    streak_atual: int
    nivel: int
    xp_proximo_nivel: int
    xp_faltando_proximo_nivel: int
    por_materia: list[XpPorMateriaOut]


class RankingEntradaOut(BaseModel):
    """What the ranking shows of a student: their name and XP, nothing that
    identifies them elsewhere (no user id, no e-mail). `voce` marks the
    authenticated student's own entry."""

    posicao: int
    nome: str
    xp: int
    voce: bool


class RankingOut(BaseModel):
    entradas: list[RankingEntradaOut]
    # The authenticated student's own place, also when it is outside `entradas`.
    # Null when they have no XP in this ranking yet.
    minha_posicao: int | None
    meu_xp: int
