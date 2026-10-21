from uuid import UUID

from fastapi import APIRouter, Query

from app.core.autorizacao import is_admin
from app.core.exceptions import MateriaNaoEncontradaException
from app.deps import (
    CurrentUserId,
    MateriaRepo,
    SettingsDep,
    TemaRepo,
    TokenPayloadDep,
    TrilhaEstudandoRepo,
)
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.repositories.trilha_explorar_repository import (
    ItemExplorar,
    Ordem,
    Origem,
    TrilhaExplorarRepo,
)
from app.schemas.trilha_explorar import (
    CotaTrilhasOut,
    EstudandoOut,
    TrilhaDetalheOut,
    TrilhaExplorarOut,
    TrilhaModuloItemOut,
    TrilhaTemaItemOut,
)
from app.services import trilha_cota_service, trilha_estudo_service

router = APIRouter(prefix="/trilhas", tags=["trilhas"])


def _item_out(item: ItemExplorar) -> dict:
    return {
        "id": item.materia.id,
        "nome": item.materia.nome,
        "descricao": item.materia.descricao,
        "verificada": item.materia.owner_user_id is None,
        "autor_nome": item.autor_nome,
        "votos": item.votos,
        "meu_voto": item.meu_voto,
        "temas": item.temas,
        "modulos": item.modulos,
        "alunos": item.alunos,
        "estudando": item.estudando,
        "pronta": item.pronta,
        "created_at": item.materia.created_at,
    }


@router.get("/cota", response_model=CotaTrilhasOut)
def cota_de_trilhas(
    user_id: CurrentUserId,
    payload: TokenPayloadDep,
    repo: MateriaRepo,
    settings: SettingsDep,
) -> CotaTrilhasOut:
    """How many trilhas the student may still create this month (admins: no limit)."""
    cota = trilha_cota_service.calcular(
        user_id, repo, settings.TRILHAS_POR_MES, admin=is_admin(payload)
    )
    return CotaTrilhasOut(
        limite=cota.limite, usadas=cota.usadas, restantes=cota.restantes, reseta_em=cota.reseta_em
    )


@router.get("/explorar", response_model=list[TrilhaExplorarOut])
def explorar_trilhas(
    user_id: CurrentUserId,
    repo: TrilhaExplorarRepo,
    origem: Origem = "todas",
    ordem: Ordem = "votos",
    limite: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
) -> list[TrilhaExplorarOut]:
    """Verified (admin) and community trilhas to browse, filtered by `origem` and
    ranked by `ordem`. Trilhas with nothing ready to study are left out, except
    the student's own."""
    itens = repo.listar(user_id, origem, ordem, limite, offset)
    return [TrilhaExplorarOut(**_item_out(i)) for i in itens]


@router.get("/{materia_id}", response_model=TrilhaDetalheOut)
def obter_trilha_detalhe(
    materia_id: UUID,
    user_id: CurrentUserId,
    repo: TrilhaExplorarRepo,
    tema_repo: TemaRepo,
) -> TrilhaDetalheOut:
    item = repo.obter(user_id, materia_id)
    if item is None:
        raise MateriaNaoEncontradaException(materia_id)
    conteudo = []
    for tema in tema_repo.list_by_materia_with_modulos(materia_id):
        modulos = sorted(
            (m for m in tema.modulos if m.status == MODULO_STATUS_PRONTO), key=lambda m: m.ordem
        )
        if modulos:
            conteudo.append(
                TrilhaTemaItemOut(
                    id=tema.id,
                    titulo=tema.titulo,
                    ordem=tema.ordem,
                    modulos=[
                        TrilhaModuloItemOut(id=m.id, titulo=m.titulo, ordem=m.ordem)
                        for m in modulos
                    ],
                )
            )
    conteudo.sort(key=lambda t: t.ordem)
    return TrilhaDetalheOut(**_item_out(item), conteudo=conteudo)


@router.post("/{materia_id}/estudar", response_model=EstudandoOut)
def estudar_trilha(
    materia_id: UUID,
    user_id: CurrentUserId,
    materia_repo: MateriaRepo,
    estudando_repo: TrilhaEstudandoRepo,
) -> EstudandoOut:
    trilha_estudo_service.estudar(user_id, materia_id, materia_repo, estudando_repo)
    return EstudandoOut(materia_id=materia_id, estudando=True)


@router.delete("/{materia_id}/estudar", response_model=EstudandoOut)
def parar_de_estudar_trilha(
    materia_id: UUID,
    user_id: CurrentUserId,
    materia_repo: MateriaRepo,
    estudando_repo: TrilhaEstudandoRepo,
) -> EstudandoOut:
    trilha_estudo_service.parar_de_estudar(user_id, materia_id, materia_repo, estudando_repo)
    return EstudandoOut(materia_id=materia_id, estudando=False)
