"""Study-summary generation for the Biblioteca.

Two modes:
- Module-scoped conversations (`conversa.modulo_id` is set): aggregates every
  conversation the student had about that módulo and produces one summary per
  (user, módulo).  Regenerating replaces it in place.
- Free conversations (`conversa.modulo_id` is None): produces one summary per
  (user, conversa) from the conversation alone, without module content.

Both modes produce the same structured template (RF4/RF5), rendered to PDF on
demand via `resumo_pdf_service`.
"""

import uuid

from sqlalchemy.exc import IntegrityError

from app.ai.base import AIProvider
from app.ai.schemas import MensagemAgente, ResumoEstudoGerado
from app.core.exceptions import (
    ConteudoIndisponivelException,
    ConversaNaoEncontradaException,
    ModuloNaoEncontradoException,
)
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa
from app.models.resumo_estudo import ResumoEstudo
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.resumo_estudo_repository import ResumoEstudoRepository
from app.services.fonte_pipeline import nomes_das_fontes

_CONTEXTO_CONVERSA_MAX_CHARS = 6000


def _mensagens_para_historico(mensagens: list) -> list[MensagemAgente]:
    selecionadas: list = []
    total = 0
    for mensagem in reversed(mensagens):
        if not mensagem.conteudo:
            continue
        total += len(mensagem.conteudo)
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


def _historico_modulo(
    user_id: str, modulo_id: uuid.UUID, conversa_repo: ConversaRepository
) -> list[MensagemAgente]:
    """Aggregates every conversation the student had about a módulo."""
    conversas = conversa_repo.list_by_user_and_modulo_with_mensagens(
        user_id, modulo_id, TIPO_ALUNO
    )
    mensagens = [m for conversa in conversas for m in conversa.mensagens]
    return _mensagens_para_historico(mensagens)


def _historico_conversa(conversa: Conversa) -> list[MensagemAgente]:
    """History from a single conversation (already loaded with messages)."""
    return _mensagens_para_historico(conversa.mensagens)


def _serializar(gerado: ResumoEstudoGerado, fontes: list[str]) -> dict:
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
        "fontes": fontes,
    }


def gerar_resumo(
    user_id: str,
    conversa_id: uuid.UUID,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    resumo_repo: ResumoEstudoRepository,
    ai_provider: AIProvider,
) -> ResumoEstudo:
    conversa = conversa_repo.get_with_mensagens(conversa_id)
    if conversa is None or conversa.user_id != user_id or conversa.tipo != TIPO_ALUNO:
        raise ConversaNaoEncontradaException(conversa_id)

    if conversa.modulo_id is not None:
        return _gerar_resumo_modulo(
            user_id, conversa, conversa_repo, modulo_repo, resumo_repo, ai_provider
        )
    return _gerar_resumo_livre(conversa, resumo_repo, ai_provider)


def _gerar_resumo_modulo(
    user_id: str,
    conversa,
    conversa_repo: ConversaRepository,
    modulo_repo: ModuloRepository,
    resumo_repo: ResumoEstudoRepository,
    ai_provider: AIProvider,
) -> ResumoEstudo:
    modulo = modulo_repo.get_with_tema_e_materia(conversa.modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(conversa.modulo_id)
    if not modulo.conteudo:
        raise ConteudoIndisponivelException(
            "O módulo ainda não possui conteúdo gerado - não há contexto para o resumo."
        )

    tema = modulo.tema
    materia = tema.materia if tema is not None else None
    historico = _historico_modulo(user_id, modulo.id, conversa_repo)

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
    # The sources are the pages the tema's search actually cited, not something
    # the model is asked to recall - with none in its prompt it invented
    # placeholders ("Fontes 1" ... "Fontes 5").
    resumo.conteudo = _serializar(gerado, nomes_das_fontes(tema.fontes) if tema else [])
    resumo.modelo_ia = gerado.modelo
    resumo_repo.commit()
    resumo_repo.refresh(resumo)
    return resumo


def _preencher_resumo_livre(
    resumo: ResumoEstudo, conversa: Conversa, titulo: str, gerado: ResumoEstudoGerado
) -> None:
    resumo.conversa_id = conversa.id
    resumo.titulo = titulo
    resumo.materia_nome = None
    resumo.tema_titulo = None
    resumo.modulo_titulo = None
    # A free conversation has no tema, so there are no searched sources to cite.
    resumo.conteudo = _serializar(gerado, [])
    resumo.modelo_ia = gerado.modelo


def _gerar_resumo_livre(
    conversa: Conversa,
    resumo_repo: ResumoEstudoRepository,
    ai_provider: AIProvider,
) -> ResumoEstudo:
    historico = _historico_conversa(conversa)
    if not historico:
        raise ConteudoIndisponivelException(
            "A conversa ainda não tem mensagens - não há o que resumir."
        )

    gerado = ai_provider.gerar_resumo_estudo(
        historico,
        materia_nome=None,
        tema_titulo=None,
        modulo_titulo=None,
        conteudo_modulo=None,
    )

    titulo = conversa.titulo or "Conversa livre"

    resumo = resumo_repo.get_by_user_and_conversa(conversa.user_id, conversa.id)
    if resumo is None:
        resumo = ResumoEstudo(user_id=conversa.user_id, titulo=titulo)
        resumo_repo.add(resumo)
    _preencher_resumo_livre(resumo, conversa, titulo, gerado)

    try:
        resumo_repo.commit()
    except IntegrityError:
        # Two requests for the same conversation raced past the lookup above; the partial
        # unique index (user_id, conversa_id WHERE modulo_id IS NULL) let only one insert
        # win. Update that one instead of failing the other request.
        resumo_repo.db.rollback()
        resumo = resumo_repo.get_by_user_and_conversa(conversa.user_id, conversa.id)
        if resumo is None:
            raise
        _preencher_resumo_livre(resumo, conversa, titulo, gerado)
        resumo_repo.commit()
    resumo_repo.refresh(resumo)
    return resumo
