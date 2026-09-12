from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import EstadoProgresso


class ModuloCreate(BaseModel):
    """No `ordem` here on purpose: a new módulo is always appended after its
    tema's existing módulos - use `ModuloUpdate.ordem` to move it afterward."""

    titulo: str = Field(..., min_length=3, max_length=200)
    descricao: str | None = None


class ModuloUpdate(BaseModel):
    titulo: str | None = Field(None, min_length=3, max_length=200)
    descricao: str | None = None
    ordem: int | None = Field(None, ge=0, description="Move o módulo para esta posição.")


class ModuloOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    tema_id: UUID
    titulo: str
    descricao: str | None
    ordem: int
    status: str
    created_at: datetime


class ModuloDetailOut(BaseModel):
    """Student-facing: `conteudo` is the actual teaching material, only
    returned once the caller has confirmed `estado` isn't 'bloqueado'."""

    id: UUID
    titulo: str
    descricao: str | None
    estado: EstadoProgresso
    conteudo: str


class ConteudoModuloAdminOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    titulo: str
    conteudo: str | None
    conteudo_modelo_ia: str | None


class ConteudoModuloUpdate(BaseModel):
    conteudo: str = Field(..., min_length=1)


class RegenerarModuloRequest(BaseModel):
    instrucoes: str | None = Field(
        None,
        description=(
            "Feedback opcional sobre o que mudar nesta regeneração "
            "(ex.: 'deixe mais curto', 'adicione mais exemplos'). Se omitido, "
            "regenera do zero como antes."
        ),
    )
