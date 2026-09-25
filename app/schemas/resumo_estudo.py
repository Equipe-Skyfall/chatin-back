from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ResumoEstudoCreate(BaseModel):
    conversa_id: UUID = Field(
        ...,
        description=(
            "Conversa de origem. Precisa estar vinculada a um módulo (modulo_id) - "
            "o resumo é sempre por módulo."
        ),
    )


class ConceitoChave(BaseModel):
    termo: str
    explicacao: str


class DuvidaResolvida(BaseModel):
    pergunta: str
    resposta: str


class ResumoEstudoConteudo(BaseModel):
    """The study-summary template, stored as JSONB on the model."""

    visao_geral: str
    conceitos_chave: list[ConceitoChave] = Field(default_factory=list)
    pontos_importantes: list[str] = Field(default_factory=list)
    exemplos: list[str] = Field(default_factory=list)
    duvidas_do_aluno: list[DuvidaResolvida] = Field(default_factory=list)
    revisao_rapida: list[str] = Field(default_factory=list)
    fontes: list[str] = Field(default_factory=list)


class ResumoEstudoOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    modulo_id: UUID
    conversa_id: UUID | None
    titulo: str
    materia_nome: str | None
    tema_titulo: str | None
    modulo_titulo: str | None
    conteudo: ResumoEstudoConteudo
    modelo_ia: str | None
    created_at: datetime
    updated_at: datetime


class ResumoEstudoListOut(BaseModel):
    """Lighter shape for the Biblioteca listing - enough to group and render
    a card without shipping every summary's full `conteudo`."""

    model_config = {"from_attributes": True}

    id: UUID
    modulo_id: UUID
    titulo: str
    materia_nome: str | None
    tema_titulo: str | None
    modulo_titulo: str | None
    updated_at: datetime
