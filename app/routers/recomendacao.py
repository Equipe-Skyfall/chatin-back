from fastapi import APIRouter

from app.deps import CurrentUserId, MateriaRepo, ProgressoRepo, TentativaRepo, XpRepo
from app.schemas.recomendacao import RecomendacaoResposta
from app.services import recomendacao_service
from app.services.progresso_service import montar_progresso

router = APIRouter(tags=["recomendacao"])


@router.get("/recomendacao", response_model=RecomendacaoResposta)
def obter_recomendacao(
    user_id: CurrentUserId,
    materia_repo: MateriaRepo,
    progresso_repo: ProgressoRepo,
    xp_repo: XpRepo,
    tentativa_repo: TentativaRepo,
) -> RecomendacaoResposta:
    """The módulo to study next, from the student's own trail (official
    curriculum plus their trilhas): weak temas first, new content next, and
    reviews that are due. `recomendacao` is null when nothing is open yet."""
    materias = materia_repo.list_minhas_e_globais_with_temas_e_modulos(user_id)
    modulo_ids = [m.id for materia in materias for tema in materia.temas for m in tema.modulos]
    progresso = montar_progresso(
        materias,
        progresso_repo.list_by_user_and_modulos(user_id, modulo_ids),
        {},
        tentativa_repo.desempenho_por_tema(user_id),
    )
    recomendacao = recomendacao_service.recomendar_proximo_estudo(
        progresso, tentativa_repo.ultimo_estudo_por_modulo(user_id)
    )
    return RecomendacaoResposta(recomendacao=recomendacao)
