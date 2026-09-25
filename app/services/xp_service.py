"""XP earning rules. Called from `progresso_service.atualizar_progresso`, the
one place a completed/retaken attempt is already detected - never duplicated
elsewhere. XP is per-matéria as well as global (see `XpRepository`), so every
event is tagged with the módulo's matéria.

Rules:
- The student's very FIRST attempt at a módulo - pass or fail - earns a
  flat, tiered amount based on how well they did on it. This fires exactly
  once per módulo per student, never again even on a later retake:
    below the approval threshold  -> XP_REPROVADO  (20)
    at the threshold up to 79%    -> XP_APROVADO   (80)
    80% up to 99%                 -> XP_BOM        (100)
    100%                          -> XP_PERFEITO   (200)
- Every attempt AFTER the first (a genuine retake) only earns XP if it beats
  the student's previous best score, and only for the improvement in points -
  this is what stops retake-grinding from being free XP forever.
"""

import uuid
from dataclasses import dataclass

from app.models.xp import MOTIVO_MELHORIA_NOTA, MOTIVO_PRIMEIRA_TENTATIVA, XpEvento
from app.repositories.xp_repository import XpRepository

XP_REPROVADO = 20
XP_APROVADO = 80
XP_BOM = 100
XP_PERFEITO = 200

# Levels are a pure function of XP total - never stored, same philosophy as
# the XP total itself (see `XpRepository`). Level 1 needs NIVEL_XP_BASE XP;
# each level after that needs 20% more than the previous one's requirement
# (500, 600, 720, 864, ...). 0 XP = level 0 ("sem nível ainda").
NIVEL_XP_BASE = 500
NIVEL_CRESCIMENTO = 1.2


@dataclass(frozen=True)
class NivelInfo:
    nivel: int
    xp_proximo_nivel: int
    xp_faltando_proximo_nivel: int


def xp_necessario_para_nivel(nivel: int) -> int:
    """Cumulative XP required to be AT `nivel` (1-indexed)."""
    return round(NIVEL_XP_BASE * (NIVEL_CRESCIMENTO ** (nivel - 1)))


def calcular_nivel(xp_total: int) -> NivelInfo:
    nivel = 0
    while xp_necessario_para_nivel(nivel + 1) <= xp_total:
        nivel += 1
    proximo = xp_necessario_para_nivel(nivel + 1)
    return NivelInfo(
        nivel=nivel, xp_proximo_nivel=proximo, xp_faltando_proximo_nivel=proximo - xp_total
    )


def _xp_primeira_tentativa(pontuacao: float, limite_aprovacao: float) -> int:
    if pontuacao < limite_aprovacao:
        return XP_REPROVADO
    if pontuacao < 80:
        return XP_APROVADO
    if pontuacao < 100:
        return XP_BOM
    return XP_PERFEITO


def registrar_xp_por_tentativa(
    user_id: str,
    materia_id: uuid.UUID,
    modulo_id: uuid.UUID,
    pontuacao: float,
    limite_aprovacao: float,
    era_primeira_tentativa: bool,
    melhoria_sobre_melhor_anterior: float,
    xp_repo: XpRepository,
) -> None:
    if era_primeira_tentativa:
        xp_repo.add(
            XpEvento(
                user_id=user_id,
                materia_id=materia_id,
                modulo_id=modulo_id,
                quantidade=_xp_primeira_tentativa(pontuacao, limite_aprovacao),
                motivo=MOTIVO_PRIMEIRA_TENTATIVA,
            )
        )
    elif melhoria_sobre_melhor_anterior > 0:
        xp_repo.add(
            XpEvento(
                user_id=user_id,
                materia_id=materia_id,
                modulo_id=modulo_id,
                quantidade=round(melhoria_sobre_melhor_anterior),
                motivo=MOTIVO_MELHORIA_NOTA,
            )
        )
