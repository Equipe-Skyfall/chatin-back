from fastapi import APIRouter

from app.ai.disponibilidade import status_ia
from app.schemas.ia import IAStatusOut

router = APIRouter(tags=["ia"])

# Routes that call the AI provider while the request is open. Study material,
# quizzes (start, answer, grading, XP), progress, ranking and the trail do not.
RECURSOS_QUE_DEPENDEM_DA_IA = [
    "chat",
    "resumos_de_estudo",
    "questionario_personalizado",
    "feedback_de_tentativa",
]


@router.get("/ia/status", response_model=IAStatusOut)
def status_da_ia() -> IAStatusOut:
    """Public on purpose (no login needed) so the frontend can show the notice
    on any screen. It never calls Gemini: it reports what recent real calls saw."""
    segundos = status_ia.segundos_ate_nova_tentativa()
    disponivel = segundos == 0
    return IAStatusOut(
        disponivel=disponivel,
        tentar_novamente_em_segundos=segundos,
        recursos_afetados=[] if disponivel else RECURSOS_QUE_DEPENDEM_DA_IA,
    )
