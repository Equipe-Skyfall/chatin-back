from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, status

from app.core.autorizacao import verificar_acesso_escrita
from app.core.exceptions import (
    ConteudoModuloNaoEncontradoException,
    ModuloBloqueadoException,
    ModuloNaoEncontradoException,
    QuestionarioNaoEncontradoException,
    TemaNaoEncontradoException,
)
from app.deps import (
    AiProviderDep,
    CurrentUserId,
    LicaoRepo,
    MateriaRepo,
    ModuloRepo,
    ProgressoRepo,
    QuestionarioRepo,
    SettingsDep,
    TemaRepo,
    TokenPayloadDep,
)
from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.modulo import Modulo
from app.models.tema import Tema
from app.schemas.modulo import (
    ConteudoModuloAdminOut,
    ConteudoModuloUpdate,
    ModuloCreate,
    ModuloDetailOut,
    ModuloOut,
    ModuloUpdate,
    RegenerarModuloRequest,
)
from app.schemas.questionario import (
    AlternativaOut,
    QuestaoAdminOut,
    QuestaoCreate,
    QuestaoUpdate,
    QuestionarioCreate,
)
from app.services import curriculo_service, quiz_manual_service, trilha_pessoal_service
from app.services.progresso_service import estado_modulo, estado_tema

router = APIRouter(tags=["modulos"])


def _exigir_acesso_ao_modulo(
    modulo_id: UUID,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
) -> None:
    """404 if the módulo doesn't exist; otherwise the same write check every
    other curriculum route makes (global -> admin, own trilha -> its owner,
    anyone else's trilha -> 404)."""
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    _, materia = _tema_e_materia_do_modulo(modulo, tema_repo, materia_repo)
    verificar_acesso_escrita(materia, payload)


def _questao_admin_out(questao, resposta_correta: str) -> QuestaoAdminOut:
    return QuestaoAdminOut(
        id=questao.id,
        ordem=questao.ordem,
        enunciado=questao.enunciado,
        alternativas=[AlternativaOut(**alt) for alt in questao.alternativas],
        explicacao=questao.explicacao,
        resposta_correta=resposta_correta,
    )


def _nova_questao(body: QuestaoCreate) -> quiz_manual_service.NovaQuestao:
    return quiz_manual_service.NovaQuestao(
        enunciado=body.enunciado,
        alternativas=[{"letra": alt.letra, "texto": alt.texto} for alt in body.alternativas],
        explicacao=body.explicacao,
        resposta_correta=body.resposta_correta,
    )


def _materia_do_tema(tema: Tema, materia_repo: MateriaRepo) -> Materia:
    materia = materia_repo.get(tema.materia_id)
    if materia is None:
        raise TemaNaoEncontradoException(tema.id)
    return materia


def _tema_e_materia_do_modulo(
    modulo: Modulo, tema_repo: TemaRepo, materia_repo: MateriaRepo
) -> tuple[Tema, Materia]:
    tema = tema_repo.get(modulo.tema_id)
    if tema is None:
        raise ModuloNaoEncontradoException(modulo.id)
    return tema, _materia_do_tema(tema, materia_repo)


@router.post(
    "/temas/{tema_id}/modulos", response_model=ModuloOut, status_code=status.HTTP_201_CREATED
)
def criar_modulo(
    tema_id: UUID,
    body: ModuloCreate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
) -> Modulo:
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.criar_modulo(
        tema_id,
        body.titulo,
        body.descricao,
        settings.QUESTIONARIO_POOL_SIZE,
        tema_repo,
        modulo_repo,
        questionario_repo,
        ai_provider,
        conteudo=body.conteudo,
    )


@router.post("/temas/{tema_id}/modulos/gerar-automaticamente", response_model=list[ModuloOut])
def gerar_modulos_automaticamente(
    tema_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> list[Modulo]:
    """Asks the AI to split this tema's content into at most 5 módulos and
    generates each one's content + quiz in the background - poll
    `GET /temas/{tema_id}/modulos` for each módulo's `status` until they
    flip to `'pronto'`/`'erro'` (see `trilha_pessoal_service`). Only works
    on a tema with no módulos yet - use the endpoint above to add módulos
    one at a time otherwise. Returns immediately with an empty list; the
    módulos appear as the background task creates them."""
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)

    background_tasks.add_task(
        trilha_pessoal_service.completar_divisao_em_modulos,
        tema_id,
        settings.QUESTIONARIO_POOL_SIZE,
        ai_provider,
    )
    return []


@router.get("/temas/{tema_id}/modulos", response_model=list[ModuloOut])
def listar_modulos(
    tema_id: UUID,
    _user_id: CurrentUserId,
    tema_repo: TemaRepo,
    modulo_repo: ModuloRepo,
) -> list[Modulo]:
    if tema_repo.get(tema_id) is None:
        raise TemaNaoEncontradoException(tema_id)
    trilha_pessoal_service.reabrir_modulos_travados(modulo_repo)
    return modulo_repo.list_by_tema(tema_id)


@router.put("/temas/{tema_id}/modulos/{modulo_id}", response_model=ModuloOut)
def atualizar_modulo(
    tema_id: UUID,
    modulo_id: UUID,
    body: ModuloUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
) -> Modulo:
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.atualizar_modulo(
        tema_id, modulo_id, body.titulo, body.descricao, body.ordem, modulo_repo
    )


@router.delete("/temas/{tema_id}/modulos/{modulo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_modulo(
    tema_id: UUID,
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
) -> None:
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    curriculo_service.deletar_modulo(tema_id, modulo_id, modulo_repo)


@router.post("/temas/{tema_id}/modulos/{modulo_id}/regenerar", response_model=ModuloOut)
def regenerar_modulo(
    tema_id: UUID,
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
    body: RegenerarModuloRequest | None = None,
) -> Modulo:
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.regenerar_modulo(
        tema_id,
        modulo_id,
        settings.QUESTIONARIO_POOL_SIZE,
        tema_repo,
        modulo_repo,
        questionario_repo,
        ai_provider,
        instrucoes=body.instrucoes if body else None,
    )


@router.post(
    "/temas/{tema_id}/modulos/{modulo_id}/questionario/regenerar", response_model=ModuloOut
)
def regenerar_questionario_modulo(
    tema_id: UUID,
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
) -> Modulo:
    """Rerolls just the quiz (one AI call) from the módulo's existing
    content - unlike .../regenerar, this never touches the content itself."""
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.regenerar_questionario_modulo(
        tema_id,
        modulo_id,
        settings.QUESTIONARIO_POOL_SIZE,
        modulo_repo,
        questionario_repo,
        ai_provider,
    )


@router.post("/temas/{tema_id}/questionarios/regenerar", response_model=list[ModuloOut])
def regenerar_questionarios_tema(
    tema_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
) -> list[Modulo]:
    """Bulk version: rerolls the quiz for every módulo under this tema that
    already has content (one AI call per módulo) - content is untouched."""
    tema = tema_repo.get(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    verificar_acesso_escrita(_materia_do_tema(tema, materia_repo), payload)
    return curriculo_service.regenerar_questionarios_tema(
        tema_id,
        settings.QUESTIONARIO_POOL_SIZE,
        tema_repo,
        modulo_repo,
        questionario_repo,
        ai_provider,
    )


@router.get("/modulos/{modulo_id}", response_model=ModuloDetailOut)
def obter_modulo(
    modulo_id: UUID,
    user_id: CurrentUserId,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    progresso_repo: ProgressoRepo,
    licao_repo: LicaoRepo,
) -> ModuloDetailOut:
    modulo = modulo_repo.get(modulo_id)
    if modulo is None or modulo.status != MODULO_STATUS_PRONTO:
        raise ModuloNaoEncontradoException(modulo_id)

    tema = tema_repo.get(modulo.tema_id)
    temas_da_materia = tema_repo.list_by_materia_with_modulos(tema.materia_id)
    modulo_ids = [m.id for t in temas_da_materia for m in t.modulos]
    progresso_map = {
        p.modulo_id: p for p in progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    }

    tema_est = estado_tema(tema, temas_da_materia, progresso_map)
    tema_com_modulos = next(t for t in temas_da_materia if t.id == tema.id)
    estado = estado_modulo(modulo, tema_com_modulos.modulos, tema_est, progresso_map)
    if estado == "bloqueado":
        raise ModuloBloqueadoException()

    return ModuloDetailOut(
        id=modulo.id,
        titulo=modulo.titulo,
        descricao=modulo.descricao,
        estado=estado,
        conteudo=modulo.conteudo or "",
        start_lesson=licao_repo.existe(user_id, modulo.id),
    )


@router.get("/modulos/{modulo_id}/conteudo", response_model=ConteudoModuloAdminOut)
def obter_conteudo_modulo(
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
) -> Modulo:
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    _, materia = _tema_e_materia_do_modulo(modulo, tema_repo, materia_repo)
    verificar_acesso_escrita(materia, payload)
    if modulo.conteudo is None:
        raise ConteudoModuloNaoEncontradoException()
    return modulo


@router.put("/modulos/{modulo_id}/conteudo", response_model=ConteudoModuloAdminOut)
def atualizar_conteudo_modulo(
    modulo_id: UUID,
    body: ConteudoModuloUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
) -> Modulo:
    """Manual edit of the already-generated content - no AI call, unlike
    `POST .../modulos/{id}/regenerar`."""
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    _, materia = _tema_e_materia_do_modulo(modulo, tema_repo, materia_repo)
    verificar_acesso_escrita(materia, payload)
    return curriculo_service.editar_conteudo_modulo(modulo_id, body.conteudo, modulo_repo)


@router.get("/modulos/{modulo_id}/questoes", response_model=list[QuestaoAdminOut])
def listar_questoes(
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> list[QuestaoAdminOut]:
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    _, materia = _tema_e_materia_do_modulo(modulo, tema_repo, materia_repo)
    verificar_acesso_escrita(materia, payload)

    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise QuestionarioNaoEncontradoException(modulo_id)

    questao_ids = questionario_repo.get_questao_ids_pool(questionario.id)
    questoes = sorted(questionario_repo.get_questoes_by_ids(questao_ids), key=lambda q: q.ordem)
    gabarito_map = questionario_repo.get_gabarito_map(questao_ids)

    return [
        QuestaoAdminOut(
            id=q.id,
            ordem=q.ordem,
            enunciado=q.enunciado,
            alternativas=[AlternativaOut(**alt) for alt in q.alternativas],
            explicacao=q.explicacao,
            resposta_correta=gabarito_map[q.id],
        )
        for q in questoes
    ]


@router.put("/modulos/{modulo_id}/questoes/{questao_id}", response_model=QuestaoAdminOut)
def atualizar_questao(
    modulo_id: UUID,
    questao_id: UUID,
    body: QuestaoUpdate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> QuestaoAdminOut:
    """Manual correction of one already-generated questão - no AI call,
    unlike `POST .../modulos/{id}/regenerar`, which rerolls the whole pool."""
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    _, materia = _tema_e_materia_do_modulo(modulo, tema_repo, materia_repo)
    verificar_acesso_escrita(materia, payload)

    alternativas = (
        [{"letra": alt.letra, "texto": alt.texto} for alt in body.alternativas]
        if body.alternativas is not None
        else None
    )
    questao, resposta_correta = curriculo_service.editar_questao(
        modulo_id,
        questao_id,
        body.enunciado,
        alternativas,
        body.explicacao,
        body.resposta_correta,
        modulo_repo,
        questionario_repo,
    )
    return QuestaoAdminOut(
        id=questao.id,
        ordem=questao.ordem,
        enunciado=questao.enunciado,
        alternativas=[AlternativaOut(**alt) for alt in questao.alternativas],
        explicacao=questao.explicacao,
        resposta_correta=resposta_correta,
    )


@router.post(
    "/modulos/{modulo_id}/questionario",
    response_model=list[QuestaoAdminOut],
    status_code=status.HTTP_201_CREATED,
)
def criar_questionario_manual(
    modulo_id: UUID,
    body: QuestionarioCreate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> list[QuestaoAdminOut]:
    """Writes the módulo's quiz by hand (no AI call). The módulo must not have
    one yet; the order of `questoes` is the order kept."""
    _exigir_acesso_ao_modulo(modulo_id, payload, modulo_repo, tema_repo, materia_repo)
    criadas = quiz_manual_service.criar_questionario(
        modulo_id, [_nova_questao(q) for q in body.questoes], modulo_repo, questionario_repo
    )
    return [_questao_admin_out(questao, resposta) for questao, resposta in criadas]


@router.post(
    "/modulos/{modulo_id}/questoes",
    response_model=QuestaoAdminOut,
    status_code=status.HTTP_201_CREATED,
)
def adicionar_questao(
    modulo_id: UUID,
    body: QuestaoCreate,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> QuestaoAdminOut:
    """Appends one questão to the módulo's existing quiz."""
    _exigir_acesso_ao_modulo(modulo_id, payload, modulo_repo, tema_repo, materia_repo)
    questao, resposta = quiz_manual_service.adicionar_questao(
        modulo_id, _nova_questao(body), modulo_repo, questionario_repo
    )
    return _questao_admin_out(questao, resposta)


@router.delete("/modulos/{modulo_id}/questoes/{questao_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_questao(
    modulo_id: UUID,
    questao_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> None:
    _exigir_acesso_ao_modulo(modulo_id, payload, modulo_repo, tema_repo, materia_repo)
    quiz_manual_service.remover_questao(modulo_id, questao_id, modulo_repo, questionario_repo)


@router.delete("/modulos/{modulo_id}/questionario", status_code=status.HTTP_204_NO_CONTENT)
def remover_questionario(
    modulo_id: UUID,
    _user_id: CurrentUserId,
    payload: TokenPayloadDep,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    questionario_repo: QuestionarioRepo,
) -> None:
    _exigir_acesso_ao_modulo(modulo_id, payload, modulo_repo, tema_repo, materia_repo)
    quiz_manual_service.remover_questionario(modulo_id, modulo_repo, questionario_repo)
