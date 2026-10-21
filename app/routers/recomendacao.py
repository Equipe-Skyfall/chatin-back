from fastapi import APIRouter, Query

from app.deps import CurrentUserId, MateriaRepo, ProgressoRepo, TentativaRepo
from app.schemas.recomendacao import RecomendacoesResposta
from app.services import recomendacao_service

router = APIRouter(tags=["recomendacao"])


@router.get("/recomendacao", response_model=RecomendacoesResposta)
def obter_recomendacoes(
    user_id: CurrentUserId,
    materia_repo: MateriaRepo,
    progresso_repo: ProgressoRepo,
    tentativa_repo: TentativaRepo,
    limite: int = Query(
        recomendacao_service.LIMITE_PADRAO, ge=1, le=recomendacao_service.LIMITE_MAXIMO
    ),
) -> RecomendacoesResposta:
    """The módulos to study next, most urgent first: weak temas, new content
    and reviews that are due. Empty when nothing is open to the student yet."""
    return RecomendacoesResposta(
        recomendacoes=recomendacao_service.listar_recomendacoes(
            user_id, materia_repo, progresso_repo, tentativa_repo, limite
        )
    )
