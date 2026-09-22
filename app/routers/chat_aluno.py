from uuid import UUID

from fastapi import APIRouter, BackgroundTasks

from app.ai.adk_provider import AdkProvider
from app.ai.schemas import FerramentaContexto
from app.core.exceptions import ConversaNaoEncontradaException, ModuloNaoEncontradoException
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
    VotoRepo,
    XpRepo,
)
from app.models.conversa import TIPO_ALUNO, Conversa
from app.schemas.chat import (
    AlunoChatMensagemInput,
    ChatRespostaOut,
    ConversaOut,
    MensagemOut,
    ResumoConversaOut,
)
from app.services import chat_aluno_service

router = APIRouter(prefix="/chat", tags=["chat-aluno"])


@router.post("", response_model=ChatRespostaOut)
def enviar_mensagem(
    body: AlunoChatMensagemInput,
    user_id: CurrentUserId,
    conversa_repo: ConversaRepo,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    xp_repo: XpRepo,
    progresso_repo: ProgressoRepo,
    voto_repo: VotoRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> ChatRespostaOut:
    if body.conversa_id is not None:
        conversa = conversa_repo.get(body.conversa_id)
        if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
            raise ConversaNaoEncontradaException(body.conversa_id)
    else:
        if body.modulo_id is not None and modulo_repo.get(body.modulo_id) is None:
            raise ModuloNaoEncontradoException(body.modulo_id)
        conversa = Conversa(
            user_id=user_id,
            titulo=body.texto[:200],
            tipo=TIPO_ALUNO,
            modulo_id=body.modulo_id,
        )
        conversa_repo.add(conversa)
        conversa_repo.commit()
        conversa_repo.refresh(conversa)

    ctx = FerramentaContexto(
        materia_repo=materia_repo,
        tema_repo=tema_repo,
        modulo_repo=modulo_repo,
        questionario_repo=questionario_repo,
        xp_repo=xp_repo,
        progresso_repo=progresso_repo,
        voto_repo=voto_repo,
        ai_provider=ai_provider,
        pool_size=settings.QUESTIONARIO_POOL_SIZE,
        user_id=user_id,
        conversa_id=conversa.id,
        background_tasks=background_tasks,
    )
    resposta = chat_aluno_service.enviar_mensagem(
        conversa,
        body.texto,
        conversa_repo,
        modulo_repo,
        ai_provider,
        ctx,
        settings.MEMORIA_JANELA_MENSAGENS,
    )
    return ChatRespostaOut(conversa_id=conversa.id, resposta=resposta)


@router.get("", response_model=list[ConversaOut])
def listar_conversas(user_id: CurrentUserId, conversa_repo: ConversaRepo) -> list[Conversa]:
    return conversa_repo.list_by_user(user_id, TIPO_ALUNO)


@router.get("/resumos", response_model=list[ResumoConversaOut])
def listar_resumos(
    user_id: CurrentUserId, conversa_repo: ConversaRepo, ai_provider: AiProviderDep
) -> list[ResumoConversaOut]:
    """One summary per conversation - generated/refreshed lazily here if it's
    missing or stale, not kept up to date on every message (see
    `chat_aluno_service.obter_ou_gerar_resumo`)."""
    conversas = conversa_repo.list_by_user(user_id, TIPO_ALUNO)
    resultado: list[ResumoConversaOut] = []
    for conversa in conversas:
        resumo = chat_aluno_service.obter_ou_gerar_resumo(conversa, conversa_repo, ai_provider)
        if resumo is None:
            continue
        resultado.append(
            ResumoConversaOut(
                conversa_id=conversa.id,
                titulo=conversa.titulo,
                resumo=resumo,
                atualizado_em=conversa.resumo_gerado_em,
            )
        )
    return resultado


@router.get("/{conversa_id}", response_model=list[MensagemOut])
def obter_historico(
    conversa_id: UUID,
    user_id: CurrentUserId,
    conversa_repo: ConversaRepo,
    ai_provider: AiProviderDep,
) -> list:
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
        raise ConversaNaoEncontradaException(conversa_id)
    if isinstance(ai_provider, AdkProvider):
        historico_adk = ai_provider.obter_historico_sessao(conversa_id)
        if historico_adk is not None:
            return historico_adk
    return conversa.mensagens
