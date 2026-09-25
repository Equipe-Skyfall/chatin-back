"""Runs on tema creation: auto-search sources, once, shared by every módulo
underneath it.

This is the only place the AI provider's grounded search is invoked - each
módulo's own content generation (`conteudo_modulo_pipeline`) reuses these
`fontes` rather than re-searching, which is the whole point of doing research
at the tema level while breaking the resulting content down per módulo.
"""

from collections.abc import Iterable

from app.ai.base import AIProvider
from app.core.exceptions import AppException, GeracaoConteudoFalhouException
from app.models.fonte import TIPO_BUSCA_AUTOMATICA, Fonte
from app.models.tema import STATUS_ERRO, STATUS_PRONTO, Tema
from app.repositories.tema_repository import TemaRepository


def nomes_das_fontes(fontes: Iterable[Fonte]) -> list[str]:
    """Names of the pages a tema's search actually cited, in order and without
    repeats - what a student should see as "Fontes" (the site's domain, never
    the provider's redirect link).

    Reads `metadata_["referencias"]` (one row holding every cited page). Rows
    saved before that shape existed have one row per cited page, with the
    page's domain in `metadata_["titulo"]` and its link in `origem`; a legacy
    fallback row (no `origem`) only holds a generic "Busca automática" label
    and cites nothing."""
    nomes: list[str] = []
    for fonte in fontes:
        metadata = fonte.metadata_ or {}
        referencias = metadata.get("referencias")
        if referencias is not None:
            candidatos = [r.get("titulo") for r in referencias]
        elif fonte.origem and metadata.get("titulo"):
            candidatos = [metadata["titulo"]]
        else:
            candidatos = []
        for nome in candidatos:
            if nome and nome not in nomes:
                nomes.append(nome)
    return nomes


def conteudos_para_geracao(fontes: Iterable[Fonte]) -> list[str]:
    """The source texts to feed into content generation: each distinct text
    once (rows saved before the search stored its text once repeat the same
    text per cited page), headed by the names of the pages it draws from so
    the generated content can name them."""
    grupos: dict[str, list[Fonte]] = {}
    for fonte in fontes:
        grupos.setdefault(fonte.conteudo_extraido, []).append(fonte)

    conteudos: list[str] = []
    for texto, grupo in grupos.items():
        nomes = nomes_das_fontes(grupo)
        conteudos.append(f"Fontes consultadas: {', '.join(nomes)}\n\n{texto}" if nomes else texto)
    return conteudos


def buscar_fontes_tema(tema: Tema, tema_repo: TemaRepository, ai_provider: AIProvider) -> None:
    try:
        fontes_encontradas = ai_provider.buscar_fontes(
            tema.titulo, tema.descricao, tema.direcionamento
        )
        if not fontes_encontradas:
            raise GeracaoConteudoFalhouException("nenhuma fonte encontrada pelo provedor de IA")

        for fonte_encontrada in fontes_encontradas:
            fonte = Fonte(
                tema_id=tema.id,
                tipo=TIPO_BUSCA_AUTOMATICA,
                origem=fonte_encontrada.origem,
                conteudo_extraido=fonte_encontrada.conteudo,
                metadata_={
                    "titulo": fonte_encontrada.titulo,
                    "referencias": [
                        {"titulo": r.titulo, "origem": r.origem}
                        for r in fonte_encontrada.referencias
                    ],
                },
            )
            tema_repo.adicionar_fonte(fonte)

        tema_repo.atualizar_status(tema, STATUS_PRONTO)
        tema_repo.commit()
    except AppException:
        tema_repo.db.rollback()
        tema_repo.atualizar_status(tema, STATUS_ERRO)
        tema_repo.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - map any unexpected failure to the erro status too
        tema_repo.db.rollback()
        tema_repo.atualizar_status(tema, STATUS_ERRO)
        tema_repo.commit()
        raise GeracaoConteudoFalhouException(str(exc)) from exc
