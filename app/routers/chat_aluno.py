from uuid import UUID

from fastapi import APIRouter

from app.core.autorizacao import verificar_acesso_leitura
from app.core.exceptions import ConversaNaoEncontradaException, ModuloNaoEncontradoException
from app.deps import (
    AiProviderDep,
    ConversaRepo,
    CurrentUserId,
    MateriaRepo,
    ModuloRepo,
    RedisCliente,
    SettingsDep,
    TemaRepo,
    TokenPayloadDep,
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
    payload: TokenPayloadDep,
    user_id: CurrentUserId,
    conversa_repo: ConversaRepo,
    modulo_repo: ModuloRepo,
    tema_repo: TemaRepo,
    materia_repo: MateriaRepo,
    ai_provider: AiProviderDep,
    redis_cliente: RedisCliente,
    settings: SettingsDep,
) -> ChatRespostaOut:
    if body.conversa_id is not None:
        conversa = conversa_repo.get(body.conversa_id)
        if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
            raise ConversaNaoEncontradaException(body.conversa_id)
    else:
        if body.modulo_id is not None:
            modulo = modulo_repo.get(body.modulo_id)
            if modulo is None:
                raise ModuloNaoEncontradoException(body.modulo_id)
            tema = tema_repo.get(modulo.tema_id)
            materia = tema and materia_repo.get(tema.materia_id)
            if tema is None or materia is None:
                raise ModuloNaoEncontradoException(body.modulo_id)
            verificar_acesso_leitura(materia, payload)
        conversa = Conversa(
            user_id=user_id,
            titulo=body.texto[:200],
            tipo=TIPO_ALUNO,
            modulo_id=body.modulo_id,
        )
        conversa_repo.add(conversa)
        conversa_repo.commit()
        conversa_repo.refresh(conversa)

    resposta = chat_aluno_service.enviar_mensagem(
        conversa,
        body.texto,
        conversa_repo,
        modulo_repo,
        ai_provider,
        redis_cliente,
        settings.MEMORIA_JANELA_MENSAGENS,
        settings.MEMORIA_LONGO_PRAZO_LIMITE,
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
def obter_historico(conversa_id: UUID, user_id: CurrentUserId, conversa_repo: ConversaRepo) -> list:
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
        raise ConversaNaoEncontradaException(conversa_id)
    return conversa.mensagens
