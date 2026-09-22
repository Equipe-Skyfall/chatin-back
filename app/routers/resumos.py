from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.exceptions import ResumoEstudoNaoEncontradoException
from app.deps import (
    AiProviderDep,
    ConversaRepo,
    CurrentUserId,
    ModuloRepo,
    ResumoEstudoRepo,
)
from app.models.resumo_estudo import ResumoEstudo
from app.schemas.resumo_estudo import (
    ResumoEstudoCreate,
    ResumoEstudoListOut,
    ResumoEstudoOut,
)
from app.services import resumo_estudo_service, resumo_pdf_service

router = APIRouter(prefix="/resumos", tags=["resumos"])


@router.post("", response_model=ResumoEstudoOut, status_code=status.HTTP_201_CREATED)
def gerar_resumo(
    body: ResumoEstudoCreate,
    user_id: CurrentUserId,
    conversa_repo: ConversaRepo,
    modulo_repo: ModuloRepo,
    resumo_repo: ResumoEstudoRepo,
    ai_provider: AiProviderDep,
) -> ResumoEstudo:
    """Generates (or regenerates) the study summary for the módulo behind the
    conversation, saving it to the Biblioteca."""
    return resumo_estudo_service.gerar_resumo(
        user_id, body.conversa_id, conversa_repo, modulo_repo, resumo_repo, ai_provider
    )


@router.get("", response_model=list[ResumoEstudoListOut])
def listar_resumos(
    user_id: CurrentUserId,
    resumo_repo: ResumoEstudoRepo,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    materia_id: UUID | None = None,
) -> list[ResumoEstudo]:
    """The caller's own summaries only (filtered by the JWT's user id),
    paginated."""
    return resumo_repo.list_by_user(user_id, limit, offset, materia_id)


@router.get("/{resumo_id}", response_model=ResumoEstudoOut)
def obter_resumo(
    resumo_id: UUID, user_id: CurrentUserId, resumo_repo: ResumoEstudoRepo
) -> ResumoEstudo:
    resumo = resumo_repo.get(resumo_id)
    if resumo is None or resumo.user_id != user_id:
        raise ResumoEstudoNaoEncontradoException(resumo_id)
    return resumo


@router.get("/{resumo_id}/pdf")
def baixar_resumo_pdf(
    resumo_id: UUID, user_id: CurrentUserId, resumo_repo: ResumoEstudoRepo
) -> Response:
    resumo = resumo_repo.get(resumo_id)
    if resumo is None or resumo.user_id != user_id:
        raise ResumoEstudoNaoEncontradoException(resumo_id)
    pdf_bytes = resumo_pdf_service.render_resumo_pdf(resumo)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="resumo-{resumo.id}.pdf"'},
    )
