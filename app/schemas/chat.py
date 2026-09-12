from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMensagemInput(BaseModel):
    texto: str = Field(..., min_length=1)
    conversa_id: UUID | None = None


class AlunoChatMensagemInput(BaseModel):
    texto: str = Field(..., min_length=1)
    conversa_id: UUID | None = None
    modulo_id: UUID | None = Field(
        None,
        description=(
            "Só é usado ao iniciar uma conversa nova (conversa_id omitido) - "
            "ancora as respostas da IA no conteúdo deste módulo."
        ),
    )


class ChatRespostaOut(BaseModel):
    conversa_id: UUID
    resposta: str


class ConversaOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    titulo: str | None
    modulo_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class MensagemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    papel: str
    conteudo: str | None
    chamadas_ferramentas: list[dict[str, Any]] | None
    created_at: datetime


class ResumoConversaOut(BaseModel):
    conversa_id: UUID
    titulo: str | None
    resumo: str
    atualizado_em: datetime
