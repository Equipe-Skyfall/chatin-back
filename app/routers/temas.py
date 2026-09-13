from uuid import UUID

from fastapi import APIRouter, status

from app.core.autorizacao import verificar_acesso_escrita, verificar_acesso_leitura
from app.core.exceptions import (
    MateriaNaoEncontradaException,
    TemaBloqueadoException,
    TemaNaoEncontradoException,
)
from app.deps import (
    AiProviderDep,
    CurrentUserId,
    MateriaRepo,
    ProgressoRepo,
    TemaRepo,
    TokenPayloadDep,
)
from app.models.materia import Materia
from app.models.tema import STATUS_PRONTO, Tema
from app.schemas.tema import ModuloResumidoOut, TemaCreate, TemaDetailOut, TemaOut, TemaUpdate
from app.schemas.trilha import TrilhaOut
from app.services import curriculo_service
from app.services.progresso_service import estado_tema, modulos_do_tema_com_estado, montar_trilha

router = APIRouter(tags=["temas"])


def _materia_do_tema(tema: Tema, materia_repo: MateriaRepo) -> Materia:
    materia = materia_repo.get(tema.materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(tema.materia_id)
    return materia


@router.post(
    "/materias/{materia_id}/temas", response_model=TemaOut, status_code=status.HTTP_201_CREATED
)
def criar_tema(
    materia_id: UUID,
    body: TemaCreate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
    ai_provider: AiProviderDep,
) -> Tema:
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_escrita(materia, payload)
    return curriculo_service.criar_tema(
        materia_id,
        body.titulo,
        body.descricao,
        materia_repo,
        tema_repo,
        ai_provider,
        direcionamento=body.direcionamento,
    )


@router.get("/materias/{materia_id}/temas", response_model=list[TemaOut])
def listar_temas(
    materia_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
) -> list[Tema]:
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    verificar_acesso_leitura(materia, payload)
    return tema_repo.list_by_materia(materia_id)


@router.put("/materias/{materia_id}/temas/{tema_id}", response_model=TemaOut)
def atualizar_tema(
    materia_id: UUID,
    tema_id: UUID,
    body: TemaUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
) -> Tema:
    tema = tema_repo.get(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.atualizar_tema(
        materia_id, tema_id, body.titulo, body.descricao, body.ordem, tema_repo, body.direcionamento
    )


@router.delete("/materias/{materia_id}/temas/{tema_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_tema(
    materia_id: UUID,
    tema_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
) -> None:
    tema = tema_repo.get(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    curriculo_service.deletar_tema(materia_id, tema_id, tema_repo)


@router.post("/materias/{materia_id}/temas/{tema_id}/regenerar", response_model=TemaOut)
def regenerar_tema(
    materia_id: UUID,
    tema_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
    ai_provider: AiProviderDep,
) -> Tema:
    tema = tema_repo.get(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.regenerar_tema(materia_id, tema_id, tema_repo, ai_provider)


@router.get("/trilha", response_model=TrilhaOut)
def obter_trilha(
    user_id: CurrentUserId, materia_repo: MateriaRepo, progresso_repo: ProgressoRepo
) -> TrilhaOut:
    """The one shared, admin-curated curriculum - never a student's personal
    trilha (see `GET /materias` for "globais + minhas")."""
    materias = materia_repo.list_globais_with_temas_e_modulos()
    modulo_ids = [m.id for materia in materias for tema in materia.temas for m in tema.modulos]
    progresso_rows = progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    return montar_trilha(materias, progresso_rows)


@router.get("/temas/{tema_id}", response_model=TemaDetailOut)
def obter_tema(
    tema_id: UUID,
    user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    progresso_repo: ProgressoRepo,
) -> TemaDetailOut:
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None or tema.status != STATUS_PRONTO:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_leitura(_materia_do_tema(tema, materia_repo), payload)

    temas_da_materia = tema_repo.list_by_materia_with_modulos(tema.materia_id)
    modulo_ids = [m.id for t in temas_da_materia for m in t.modulos]
    progresso_map = {
        p.modulo_id: p for p in progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    }

    estado = estado_tema(tema, temas_da_materia, progresso_map)
    if estado == "bloqueado":
        raise TemaBloqueadoException()

    modulos_out = [
        ModuloResumidoOut(id=m.id, titulo=m.titulo, ordem=m.ordem, status=m.status, estado=e)
        for m, e in modulos_do_tema_com_estado(tema, progresso_map)
    ]

    return TemaDetailOut(
        id=tema.id,
        titulo=tema.titulo,
        descricao=tema.descricao,
        estado=estado,
        modulos=modulos_out,
    )
