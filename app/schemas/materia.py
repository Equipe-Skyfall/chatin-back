from datetime import datetime
from typing import Literal
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
    owner_user_id: str | None = Field(
        None,
        description=(
            "None = currículo oficial (curado por admins). Caso contrário, é uma trilha "
            "criada por um aluno - visível e votável por todos."
        ),
    )
    votos: int = Field(
        0, description="Placar líquido de votos (soma de +1/-1) - sempre 0 para currículo oficial."
    )
    created_at: datetime


class VotoInput(BaseModel):
    valor: Literal[1, -1]


class VotoOut(BaseModel):
    materia_id: UUID
    votos: int
