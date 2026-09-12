from uuid import UUID

from fastapi import APIRouter

from app.core.exceptions import (
    ModuloBloqueadoException,
    ModuloNaoEncontradoException,
    QuestionarioNaoEncontradoException,
    TentativaNaoEncontradaException,
)
from app.deps import (
    CurrentUserId,
    MateriaRepo,
    ModuloRepo,
    ProgressoRepo,
    QuestionarioRepo,
    SettingsDep,
    TemaRepo,
    TentativaRepo,
)
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.schemas.progresso import ProgressoOut
from app.schemas.questionario import AlternativaOut, QuestaoOut, TentativaIniciarOut
from app.schemas.tentativa import ResponderRequest, TentativaResultadoOut
from app.services import grading_service
from app.services.progresso_service import (
    atualizar_progresso,
    estado_modulo,
    estado_tema,
    montar_progresso,
)

router = APIRouter(tags=["tentativas"])


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

    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise QuestionarioNaoEncontradoException(modulo_id)

    tentativa, questoes = grading_service.iniciar_tentativa(
        questionario.id, user_id, settings.TENTATIVA_NUM_QUESTOES, questionario_repo, tentativa_repo
    )

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
    )


@router.post("/tentativas/{tentativa_id}/responder", response_model=TentativaResultadoOut)
def responder_tentativa(
    tentativa_id: UUID,
    body: ResponderRequest,
    user_id: CurrentUserId,
    questionario_repo: QuestionarioRepo,
    tentativa_repo: TentativaRepo,
    progresso_repo: ProgressoRepo,
    settings: SettingsDep,
) -> TentativaResultadoOut:
    tentativa = tentativa_repo.get(tentativa_id)
    if tentativa is None or tentativa.user_id != user_id:
        raise TentativaNaoEncontradaException(tentativa_id)

    tentativa, resultados = grading_service.responder_tentativa(
        tentativa, body.respostas, questionario_repo, tentativa_repo
    )

    modulo_id = tentativa.questionario.modulo_id
    atualizar_progresso(
        progresso_repo,
        user_id,
        modulo_id,
        float(tentativa.pontuacao),
        settings.PONTUACAO_MINIMA_APROVACAO,
    )
    progresso_repo.commit()

    return TentativaResultadoOut(
        id=tentativa.id,
        questionario_id=tentativa.questionario_id,
        pontuacao=float(tentativa.pontuacao),
        total_questoes=tentativa.total_questoes,
        total_corretas=tentativa.total_corretas,
        resultados=resultados,
    )


@router.get("/progresso", response_model=ProgressoOut)
def obter_progresso(
    user_id: CurrentUserId, materia_repo: MateriaRepo, progresso_repo: ProgressoRepo
) -> ProgressoOut:
    materias = materia_repo.list_all_with_temas_e_modulos()
    modulo_ids = [m.id for materia in materias for tema in materia.temas for m in tema.modulos]
    progresso_rows = progresso_repo.list_by_user_and_modulos(user_id, modulo_ids)
    return montar_progresso(materias, progresso_rows)
