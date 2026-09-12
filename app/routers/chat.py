from uuid import UUID

from fastapi import APIRouter

from app.core.exceptions import ConversaNaoEncontradaException
from app.deps import (
    AdminUserId,
    AiProviderDep,
    ConversaRepo,
    MateriaRepo,
    ModuloRepo,
    QuestionarioRepo,
    SettingsDep,
    TemaRepo,
)
from app.models.conversa import Conversa
from app.schemas.chat import ChatMensagemInput, ChatRespostaOut, ConversaOut, MensagemOut
from app.services import agent_service
from app.services.agent_tools import FerramentaContexto

router = APIRouter(prefix="/admin/chat", tags=["chat"])


@router.post("", response_model=ChatRespostaOut)
def enviar_mensagem(
    body: ChatMensagemInput,
    admin_id: AdminUserId,
    conversa_repo: ConversaRepo,
    materia_repo: MateriaRepo,
    tema_repo: TemaRepo,
    modulo_repo: ModuloRepo,
    questionario_repo: QuestionarioRepo,
    ai_provider: AiProviderDep,
    settings: SettingsDep,
) -> ChatRespostaOut:
    if body.conversa_id is not None:
        conversa = conversa_repo.get(body.conversa_id)
        if conversa is None or conversa.user_id != admin_id:
            raise ConversaNaoEncontradaException(body.conversa_id)
    else:
        conversa = Conversa(user_id=admin_id, titulo=body.texto[:200])
        conversa_repo.add(conversa)
        conversa_repo.commit()
        conversa_repo.refresh(conversa)

    ctx = FerramentaContexto(
        materia_repo=materia_repo,
        tema_repo=tema_repo,
        modulo_repo=modulo_repo,
        questionario_repo=questionario_repo,
        ai_provider=ai_provider,
        pool_size=settings.QUESTIONARIO_POOL_SIZE,
    )
    resposta = agent_service.processar_mensagem(
        conversa, body.texto, conversa_repo, ctx, ai_provider, settings.AGENTE_MAX_ITERACOES
    )
    return ChatRespostaOut(conversa_id=conversa.id, resposta=resposta)


@router.get("", response_model=list[ConversaOut])
def listar_conversas(admin_id: AdminUserId, conversa_repo: ConversaRepo) -> list[Conversa]:
    return conversa_repo.list_by_user(admin_id)


@router.get("/{conversa_id}", response_model=list[MensagemOut])
def obter_historico(conversa_id: UUID, admin_id: AdminUserId, conversa_repo: ConversaRepo) -> list:
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != admin_id:
        raise ConversaNaoEncontradaException(conversa_id)
    return conversa.mensagens
