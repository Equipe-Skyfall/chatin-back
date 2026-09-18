from uuid import UUID

from fastapi import APIRouter

from app.core.exceptions import (
    ModuloBloqueadoException,
    ModuloNaoEncontradoException,
    QuestionarioNaoEncontradoException,
    TemaBloqueadoException,
    TemaNaoEncontradoException,
    TentativaNaoEncontradaException,
)
from app.deps import (
    AiProviderDep,
    ConversaRepo,
    CurrentUserId,
    MateriaRepo,
    ModuloRepo,
    ProgressoRepo,
    QuestionarioRepo,
    SettingsDep,
    TemaRepo,
    TentativaRepo,
    XpRepo,
)
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.tema import STATUS_PRONTO as TEMA_STATUS_PRONTO
from app.schemas.progresso import ProgressoOut
from app.schemas.questionario import AlternativaOut, QuestaoOut, TentativaIniciarOut
from app.schemas.tentativa import ResponderRequest, TentativaHistoricoOut, TentativaResultadoOut
from app.services import grading_service, questionario_personalizado_service
from app.services.progresso_service import (
    atualizar_progresso,
    estado_modulo,
    estado_tema,
    montar_progresso,
)

router = APIRouter(tags=["tentativas"])


def _verificar_modulo_disponivel(
    modulo_id: UUID,
    user_id: str,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    progresso_repo: ProgressoRepo,
):
    """Shared by `iniciar_tentativa` and `gerar_questionario_personalizado` -
    both need the módulo ready and unlocked before starting anything."""
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
    if estado_modulo(modulo, tema_com_modulos.modulos, tema_est, progresso_map) == "bloqueado":
        raise ModuloBloqueadoException()
    return modulo


def _tentativa_iniciar_out(tentativa, questoes: list) -> TentativaIniciarOut:
    return TentativaIniciarOut(
        tentativa_id=tentativa.id,
        questoes=[
            QuestaoOut(
                id=q.id,
                ordem=idx,
                enunciado=q.enunciado,
                alternativas=[AlternativaOut(**alt) for alt in q.alternativas],
            )
            for idx, q in enumerate(questoes)
        ],
        pratica=tentativa.pratica,
        questionario_id=tentativa.questionario_id,
        tema_id=tentativa.tema_id,
    )


@router.post("/modulos/{modulo_id}/tentativas", response_model=TentativaIniciarOut)
def iniciar_tentativa(
    modulo_id: UUID,
    user_id: CurrentUserId,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    progresso_repo: ProgressoRepo,
    questionario_repo: QuestionarioRepo,
    tentativa_repo: TentativaRepo,
    settings: SettingsDep,
) -> TentativaIniciarOut:
    _verificar_modulo_disponivel(modulo_id, user_id, modulo_repo, tema_repo, progresso_repo)

    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise QuestionarioNaoEncontradoException(modulo_id)

    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, user_id, settings.TENTATIVA_NUM_QUESTOES, questionario_repo, tentativa_repo
    )
    return _tentativa_iniciar_out(tentativa, questoes)


@router.post("/modulos/{modulo_id}/questionario-personalizado", response_model=TentativaIniciarOut)
def gerar_questionario_personalizado(
    modulo_id: UUID,
    user_id: CurrentUserId,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    progresso_repo: ProgressoRepo,
    questionario_repo: QuestionarioRepo,
    conversa_repo: ConversaRepo,
    tentativa_repo: TentativaRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
) -> TentativaIniciarOut:
    """Aluno-triggered practice quiz, grounded in the módulo's content plus
    the student's own conversation about it - unlike `iniciar_tentativa`,
    may call the AI (only for however many questions the pool is short of -
    see `questionario_personalizado_service`) and never affects progress/XP."""
    _verificar_modulo_disponivel(modulo_id, user_id, modulo_repo, tema_repo, progresso_repo)

    tentativa, questoes = questionario_personalizado_service.gerar_tentativa_personalizada(
        modulo_id,
        user_id,
        settings.QUESTIONARIO_POOL_SIZE,
        settings.TENTATIVA_NUM_QUESTOES,
        modulo_repo,
        questionario_repo,
        conversa_repo,
        tentativa_repo,
        ai_provider,
    )
    return _tentativa_iniciar_out(tentativa, questoes)


@router.post("/temas/{tema_id}/tentativas", response_model=TentativaIniciarOut)
def iniciar_tentativa_tema(
    tema_id: UUID,
    user_id: CurrentUserId,
    tema_repo: TemaRepo,
    progresso_repo: ProgressoRepo,
    questionario_repo: QuestionarioRepo,
    tentativa_repo: TentativaRepo,
    settings: SettingsDep,
) -> TentativaIniciarOut:
    """A review quiz mixing questions from every ready módulo under this
    tema - practice only, doesn't affect progress/XP (see `Tentativa`)."""
    tema = tema_repo.get(tema_id)
    if tema is None or tema.status != TEMA_STATUS_PRONTO:
        raise TemaNaoEncontradoException(tema_id)

    temas_da_materia = tema_repo.list_by_materia_with_modulos(tema.materia_id)
    modulo_ids = [m.id for t in temas_da_materia for m in t.modulos]
    progresso_map = {
        p.modulo_id: p for p in progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    }
    if estado_tema(tema, temas_da_materia, progresso_map) == "bloqueado":
        raise TemaBloqueadoException()

    tentativa, questoes = grading_service.iniciar_tentativa_tema(
        tema_id, user_id, settings.TENTATIVA_NUM_QUESTOES, questionario_repo, tentativa_repo
    )
    return _tentativa_iniciar_out(tentativa, questoes)


@router.post("/tentativas/{tentativa_id}/responder", response_model=TentativaResultadoOut)
def responder_tentativa(
    tentativa_id: UUID,
    body: ResponderRequest,
    user_id: CurrentUserId,
    questionario_repo: QuestionarioRepo,
    tentativa_repo: TentativaRepo,
    progresso_repo: ProgressoRepo,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    xp_repo: XpRepo,
    settings: SettingsDep,
) -> TentativaResultadoOut:
    tentativa = tentativa_repo.get(tentativa_id)
    if tentativa is None or tentativa.user_id != user_id:
        raise TentativaNaoEncontradaException(tentativa_id)

    tentativa, resultados = grading_service.responder_tentativa(
        tentativa, body.respostas, questionario_repo, tentativa_repo
    )

    if tentativa.questionario_id is not None and not tentativa.pratica:
        modulo_id = tentativa.questionario.modulo_id
        modulo = modulo_repo.get(modulo_id)
        tema = tema_repo.get(modulo.tema_id)
        atualizar_progresso(
            progresso_repo,
            user_id,
            modulo_id,
            tema.materia_id,
            float(tentativa.pontuacao),
            settings.PONTUACAO_MINIMA_APROVACAO,
            xp_repo,
        )
        progresso_repo.commit()
    # a tema-scoped (review) or `pratica` attempt is practice only - no progress/XP change

    return TentativaResultadoOut(
        id=tentativa.id,
        questionario_id=tentativa.questionario_id,
        tema_id=tentativa.tema_id,
        pontuacao=float(tentativa.pontuacao),
        total_questoes=tentativa.total_questoes,
        total_corretas=tentativa.total_corretas,
        resultados=resultados,
    )


@router.get("/tentativas", response_model=list[TentativaHistoricoOut])
def listar_minhas_tentativas(user_id: CurrentUserId, tentativa_repo: TentativaRepo) -> list:
    return [
        TentativaHistoricoOut(
            id=t.id,
            modulo_id=t.questionario.modulo_id if t.questionario_id else None,
            modulo_titulo=t.questionario.modulo.titulo if t.questionario_id else None,
            tema_id=t.tema_id,
            tema_titulo=t.tema.titulo if t.tema_id else None,
            status=t.status,
            pontuacao=float(t.pontuacao) if t.pontuacao is not None else None,
            total_questoes=t.total_questoes,
            total_corretas=t.total_corretas,
            created_at=t.created_at,
        )
        for t in tentativa_repo.list_by_user(user_id)
    ]


@router.get("/progresso", response_model=ProgressoOut)
def obter_progresso(
    user_id: CurrentUserId,
    materia_repo: MateriaRepo,
    progresso_repo: ProgressoRepo,
    xp_repo: XpRepo,
) -> ProgressoOut:
    materias = materia_repo.list_all_with_temas_e_modulos()
    modulo_ids = [m.id for materia in materias for tema in materia.temas for m in tema.modulos]
    progresso_rows = progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    xp_por_materia = {m.id: xp_repo.total_por_usuario_e_materia(user_id, m.id) for m in materias}
    return montar_progresso(materias, progresso_rows, xp_por_materia)
