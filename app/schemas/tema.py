from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import EstadoProgresso


class TemaCreate(BaseModel):
    """No `ordem` here on purpose: a new tema is always appended after its
    matéria's existing temas - use `TemaUpdate.ordem` to move it afterward."""

    titulo: str = Field(..., min_length=3, max_length=200)
    descricao: str | None = None
    direcionamento: str | None = Field(
        None, description="Instruções livres para a IA (estilo, profundidade, exemplos etc.)."
    )


class TemaUpdate(BaseModel):
    titulo: str | None = Field(None, min_length=3, max_length=200)
    descricao: str | None = None
    ordem: int | None = Field(None, ge=0, description="Move o tema para esta posição.")
    direcionamento: str | None = None


class TemaOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    materia_id: UUID
    titulo: str
    descricao: str | None
    ordem: int
    status: str
    direcionamento: str | None
    created_at: datetime


class ModuloResumidoOut(BaseModel):
    id: UUID
    titulo: str
    ordem: int
    status: str
    estado: EstadoProgresso


class TemaStatusOut(BaseModel):
    """The one thing to poll after `criar_minha_trilha`/`gerar-
    automaticamente` returns - `tema.status` alone only ever meant "sources
    found, ready to receive módulos", not "fully generated" (see
    `trilha_pessoal_service.calcular_status_tema`). `pronto_para_estudar`
    is the real "nothing left in flight" answer."""

    tema_id: UUID
    tema_status: str
    modulos_total: int
    modulos_prontos: int
    modulos_com_erro: int
    modulos_gerando: int
    pronto_para_estudar: bool


class TemaDetailOut(BaseModel):
    """Tema is a pure grouping node - no content of its own; teaching material
    lives on each módulo (see `ModuloDetailOut`)."""

    id: UUID
    titulo: str
    descricao: str | None
    estado: EstadoProgresso
    modulos: list[ModuloResumidoOut]
