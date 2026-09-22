"""Study-summary generation for the Biblioteca: turns a student's conversations
about one módulo (plus that módulo's teaching content) into a structured
"resumo de estudos preparatórios", persisted one-per-módulo.

Distinct from `chat_aluno_service.obter_ou_gerar_resumo`, which caches a short
3-sentence digest per conversation. This one produces an addressable library
artifact (RF4/RF5) rendered to PDF on demand.
"""

import uuid

from app.ai.base import AIProvider
from app.ai.schemas import MensagemAgente, ResumoEstudoGerado
from app.core.exceptions import (
    ConteudoIndisponivelException,
    ConversaNaoEncontradaException,
    ModuloNaoEncontradoException,
    ResumoEstudoSemModuloException,
)
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO
from app.models.resumo_estudo import ResumoEstudo
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.resumo_estudo_repository import ResumoEstudoRepository

# Caps how much of the student's own conversation text is embedded in the
# generation prompt - same reasoning as `questionario_personalizado_service`
# (bounds token cost/context size and the padding surface for prompt
# injection). Keeps the most *recent* text (the tail).
_CONTEXTO_CONVERSA_MAX_CHARS = 6000


def _historico(
    user_id: str, modulo_id: uuid.UUID, conversa_repo: ConversaRepository
) -> list[MensagemAgente]:
    """Aggregates every one of this student's conversations about the módulo
    (not just the one that triggered the generation) - the summary is
    per-módulo, so it should reflect everything the student discussed there,
    and stay the same no matter which session triggered it."""
    conversas = conversa_repo.list_by_user_and_modulo_with_mensagens(
        user_id, modulo_id, TIPO_ALUNO
    )
    mensagens = [m for conversa in conversas for m in conversa.mensagens if m.conteudo]

    selecionadas = []
    total = 0
    for mensagem in reversed(mensagens):
        total += len(mensagem.conteudo or "")
        selecionadas.append(mensagem)
        if total >= _CONTEXTO_CONVERSA_MAX_CHARS:
            break
    selecionadas.reverse()

    return [
        MensagemAgente(
            papel=PAPEL_ASSISTENTE if m.papel == PAPEL_ASSISTENTE else PAPEL_USUARIO,
            conteudo=m.conteudo,
        )
        for m in selecionadas
    ]


def _serializar(gerado: ResumoEstudoGerado) -> dict:
    return {
        "visao_geral": gerado.visao_geral,
        "conceitos_chave": [
            {"termo": c.termo, "explicacao": c.explicacao} for c in gerado.conceitos_chave
        ],
        "pontos_importantes": list(gerado.pontos_importantes),
        "exemplos": list(gerado.exemplos),
        "duvidas_do_aluno": [
            {"pergunta": d.pergunta, "resposta": d.resposta} for d in gerado.duvidas_do_aluno
        ],
        "revisao_rapida": list(gerado.revisao_rapida),
        "fontes": list(gerado.fontes),
    }


def gerar_resumo(
    user_id: str,
    conversa_id: uuid.UUID,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    resumo_repo: ResumoEstudoRepository,
    ai_provider: AIProvider,
) -> ResumoEstudo:
    """Generates (or regenerates) the study summary for the módulo behind
    `conversa_id`, upserting on (user_id, modulo_id) so there's exactly one
    per módulo. A failed AI call raises before anything is persisted, so the
    Biblioteca keeps serving whatever was already saved (RNF6)."""
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
        raise ConversaNaoEncontradaException(conversa_id)
    if conversa.modulo_id is None:
        raise ResumoEstudoSemModuloException()

    modulo = modulo_repo.get_with_tema_e_materia(conversa.modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(conversa.modulo_id)
    if not modulo.conteudo:
        raise ConteudoIndisponivelException(
            "O módulo ainda não possui conteúdo gerado - não há contexto para o resumo."
        )

    tema = modulo.tema
    materia = tema.materia if tema is not None else None
    historico = _historico(user_id, modulo.id, conversa_repo)

    gerado = ai_provider.gerar_resumo_estudo(
        historico,
        materia.nome if materia is not None else None,
        tema.titulo if tema is not None else None,
        modulo.titulo,
        modulo.conteudo,
    )

    resumo = resumo_repo.get_by_user_and_modulo(user_id, modulo.id)
    if resumo is None:
        resumo = ResumoEstudo(user_id=user_id, modulo_id=modulo.id, titulo=modulo.titulo)
        resumo_repo.add(resumo)

    resumo.conversa_id = conversa.id
    resumo.titulo = modulo.titulo
    resumo.materia_nome = materia.nome if materia is not None else None
    resumo.tema_titulo = tema.titulo if tema is not None else None
    resumo.modulo_titulo = modulo.titulo
    resumo.conteudo = _serializar(gerado)
    resumo.modelo_ia = gerado.modelo
    resumo_repo.commit()
    resumo_repo.refresh(resumo)
    return resumo
