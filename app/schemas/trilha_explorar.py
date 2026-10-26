from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TrilhaExplorarOut(BaseModel):
    id: UUID
    nome: str
    descricao: str | None
    verificada: bool = Field(
        description="True = currículo oficial (criado por admin). False = trilha de um aluno."
    )
    autor_nome: str | None = Field(None, description="Nome do aluno autor; nulo se verificada.")
    votos: int
    meu_voto: Literal[1, -1] | None = None
    temas: int = Field(description="Temas com pelo menos um módulo pronto.")
    modulos: int = Field(description="Módulos prontos.")
    alunos: int = Field(description="Alunos estudando (adotaram, têm progresso ou são o autor).")
    estudando: bool = Field(description="Já faz parte das trilhas deste aluno.")
    propria: bool = Field(description="Foi criada por este aluno (não sai da lista de estudos).")
    pronta: bool = Field(description="Tem ao menos um módulo pronto para estudar.")
    created_at: datetime


class TrilhaModuloItemOut(BaseModel):
    id: UUID
    titulo: str
    ordem: int


class TrilhaTemaItemOut(BaseModel):
    id: UUID
    titulo: str
    ordem: int
    modulos: list[TrilhaModuloItemOut]


class TrilhaDetalheOut(TrilhaExplorarOut):
    conteudo: list[TrilhaTemaItemOut]


class CotaTrilhasOut(BaseModel):
    limite: int | None = Field(description="Nulo = sem limite (admin).")
    usadas: int
    restantes: int | None
    reseta_em: datetime


class EstudandoOut(BaseModel):
    materia_id: UUID
    estudando: bool


class TrilhaVerificarIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    descricao: str | None = Field(None, max_length=2000)


class TrilhaSimilarOut(TrilhaExplorarOut):
    similaridade: float = Field(
        description="Similaridade de cosseno com a trilha proposta (0 a 1)."
    )


class TrilhaVerificacaoOut(BaseModel):
    status: Literal["nova", "parecidas", "igual"] = Field(
        description=(
            "igual: já existe uma trilha equivalente (use-a); parecidas: há trilhas próximas "
            "(ofereça até 3); nova: pode criar."
        )
    )
    nome_normalizado: str = Field(description="Título corrigido pela IA; use-o ao criar.")
    similares: list[TrilhaSimilarOut]
