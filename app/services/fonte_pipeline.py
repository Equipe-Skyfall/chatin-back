"""Runs on tema creation: auto-search sources, once, shared by every módulo
underneath it.

This is the only place the AI provider's grounded search is invoked - each
módulo's own content generation (`conteudo_modulo_pipeline`) reuses these
`fontes` rather than re-searching, which is the whole point of doing research
at the tema level while breaking the resulting content down per módulo.
"""

from app.ai.base import AIProvider
from app.core.exceptions import AppException, GeracaoConteudoFalhouException
from app.models.fonte import TIPO_BUSCA_AUTOMATICA, Fonte
from app.models.tema import STATUS_ERRO, STATUS_PRONTO, Tema
from app.repositories.tema_repository import TemaRepository


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
                metadata_={"titulo": fonte_encontrada.titulo},
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
