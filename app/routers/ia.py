from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.ai.disponibilidade import status_ia
from app.deps import AdminUserId, IaConsumoRepo
from app.schemas.ia import ConsumoItemOut, IAConsumoOut, IAStatusOut

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


LIMITE_USUARIOS_NO_CONSUMO = 10


@router.get("/ia/consumo", response_model=IAConsumoOut)
def consumo_da_ia(
    _admin: AdminUserId,
    repo: IaConsumoRepo,
    dias: int = Query(30, ge=1, le=365),
) -> IAConsumoOut:
    """AI usage for the admin (RNF7): calls, failures and, when the provider
    reported them, tokens - in total, per operation and per user."""
    desde = datetime.now(UTC) - timedelta(days=dias)
    chamadas, falhas, entrada, saida = repo.totais(desde)

    def itens(linhas):
        return [
            ConsumoItemOut(chave=chave, chamadas=c, falhas=f, tokens_entrada=e, tokens_saida=s)
            for chave, c, f, e, s in linhas
        ]

    return IAConsumoOut(
        periodo_dias=dias,
        chamadas=chamadas,
        falhas=falhas,
        tokens_entrada=entrada,
        tokens_saida=saida,
        por_operacao=itens(repo.por_operacao(desde)),
        por_usuario=itens(repo.por_usuario(desde, LIMITE_USUARIOS_NO_CONSUMO)),
    )
