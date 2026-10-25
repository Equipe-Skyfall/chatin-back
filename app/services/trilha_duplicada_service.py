"""Checks a trilha about to be created against the existing ones.

The title the student typed is first cleaned by the AI (typos, accents, caps),
then name + description are embedded (Word2Vec) and the nearest trilhas found by
cosine similarity: at or above `TRILHA_SIMILARIDADE_IGUAL` it is the same
trilha (the student should use it); between that and `TRILHA_SIMILARIDADE_PARECIDA`
the top 3 are offered. Nothing here spends the monthly quota - only actually
creating does. Any failure (no model file, AI down) degrades to "nova" (RNF6).
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.ai.base import AIProvider
from app.config import Settings
from app.models.materia import Materia
from app.repositories.materia_repository import MateriaRepository
from app.similaridade.embedding import Embedder, get_embedder
from app.similaridade.indice import IndiceTrilhas, get_indice

logger = logging.getLogger(__name__)

Status = Literal["nova", "parecidas", "igual"]
MAX_SIMILARES = 3


@dataclass(frozen=True)
class Candidata:
    materia: Materia
    similaridade: float


@dataclass(frozen=True)
class Veredito:
    status: Status
    nome_normalizado: str
    candidatas: list[Candidata] = field(default_factory=list)


def _texto(nome: str, descricao: str | None) -> str:
    return f"{nome} {descricao or ''}".strip()


def normalizar_nome(nome: str, ai_provider: AIProvider) -> str:
    try:
        return ai_provider.normalizar_titulo_trilha(nome) or nome.strip()
    except Exception:  # noqa: BLE001 - RNF6: the check never blocks creation
        logger.warning("Falha ao normalizar o título; usando o digitado.", exc_info=True)
        return nome.strip()


def verificar(
    nome: str,
    descricao: str | None,
    repo: MateriaRepository,
    ai_provider: AIProvider,
    settings: Settings,
    embedder: Embedder | None,
    indice: IndiceTrilhas | None = None,
) -> Veredito:
    nome_normalizado = normalizar_nome(nome, ai_provider)
    if embedder is None:
        return Veredito("nova", nome_normalizado)

    materias = {m.id: m for m in repo.list_publica()}
    indice = indice or get_indice(embedder.dim)
    indice.sincronizar({i: _texto(m.nome, m.descricao) for i, m in materias.items()}, embedder)

    vetor = embedder.vetor(_texto(nome_normalizado, descricao))
    if vetor is None:
        return Veredito("nova", nome_normalizado)

    candidatas = [
        Candidata(materias[materia_id], similaridade)
        for materia_id, similaridade in indice.buscar(vetor, MAX_SIMILARES)
        if materia_id in materias and similaridade >= settings.TRILHA_SIMILARIDADE_PARECIDA
    ]
    if not candidatas:
        return Veredito("nova", nome_normalizado)
    if candidatas[0].similaridade >= settings.TRILHA_SIMILARIDADE_IGUAL:
        return Veredito("igual", nome_normalizado, candidatas)
    return Veredito("parecidas", nome_normalizado, candidatas)


def verificador(repo: MateriaRepository, ai_provider: AIProvider, settings: Settings):
    """`verificar` bound to a request's repo/provider, for the chat tool's context."""

    def _verificar(nome: str, descricao: str | None) -> Veredito:
        return verificar(nome, descricao, repo, ai_provider, settings, get_embedder())

    return _verificar
