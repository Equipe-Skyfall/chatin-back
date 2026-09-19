from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MateriaCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=200)
    descricao: str | None = None


class MateriaUpdate(BaseModel):
    nome: str | None = Field(None, min_length=2, max_length=200)
    descricao: str | None = None


class MateriaOut(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    nome: str
    descricao: str | None
    created_at: datetime
