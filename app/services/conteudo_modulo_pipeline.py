"""Runs on módulo creation, before the quiz: generate that módulo's own
teaching content from the tema's already-searched `fontes` plus the módulo's
own title/focus. No new search happens here - `fonte_pipeline` already did
that once, at tema-creation time, shared by every módulo underneath it.
"""

from app.ai.base import AIProvider
from app.core.exceptions import (
    AppException,
    ConteudoIndisponivelException,
    GeracaoConteudoFalhouException,
)
from app.models.modulo import STATUS_ERRO, Modulo
from app.models.tema import Tema
from app.repositories.modulo_repository import ModuloRepository


def gerar_conteudo_modulo(
    modulo: Modulo,
    tema: Tema,
    modulo_repo: ModuloRepository,
    ai_provider: AIProvider,
    conteudo_ja_coberto: list[str] | None = None,
    instrucoes_regeneracao: str | None = None,
) -> None:
    """`conteudo_ja_coberto` is the actual content of earlier módulos (by
    ordem) under this same tema, if any - passed through so this módulo
    continues rather than repeating them. Populated by both the one-at-a-time
    creation flow and the auto-split flow (see `curriculo_service`).
    `instrucoes_regeneracao` is admin feedback on what to change, only set
    when this runs as part of `regenerar_modulo`."""
    if not tema.fontes:
        raise ConteudoIndisponivelException(
            "O tema ainda não possui fontes pesquisadas para gerar conteúdo do módulo."
        )

    try:
        conteudo_gerado = ai_provider.gerar_conteudo_modulo(
            tema.titulo,
            modulo.titulo,
            modulo.descricao,
            [f.conteudo_extraido for f in tema.fontes],
            tema.direcionamento,
            conteudo_ja_coberto,
            instrucoes_regeneracao,
        )
        modulo_repo.definir_conteudo(modulo, conteudo_gerado.conteudo, conteudo_gerado.modelo)
        modulo_repo.commit()
    except AppException:
        modulo_repo.db.rollback()
        modulo_repo.atualizar_status(modulo, STATUS_ERRO)
        modulo_repo.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        modulo_repo.db.rollback()
        modulo_repo.atualizar_status(modulo, STATUS_ERRO)
        modulo_repo.commit()
        raise GeracaoConteudoFalhouException(str(exc)) from exc
