"""Turns a grounded search's result (synthesized text + grounding chunks) into
`FonteEncontrada`s. Shared by every provider - `google_search` grounding hands
back the same `grounding_chunks` shape through the raw SDK and through the ADK.
"""

import logging
from typing import Any

from app.ai.schemas import FonteEncontrada, ReferenciaFonte

logger = logging.getLogger(__name__)


def fontes_a_partir_do_grounding(
    texto: str, chunks: list[Any], tema_titulo: str
) -> list[FonteEncontrada]:
    """The search returns a single synthesized `texto` covering every cited
    page, so it becomes ONE `FonteEncontrada` (stored once) carrying the cited
    pages as `referencias` - not one copy of the same text per chunk, which
    multiplied the tokens fed into module generation."""
    referencias: list[ReferenciaFonte] = []
    vistas: set[tuple[str, str | None]] = set()
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        titulo = (
            getattr(web, "title", None)
            or getattr(web, "domain", None)
            or f"Fonte sobre {tema_titulo}"
        )
        origem = getattr(web, "uri", None)
        if (titulo, origem) in vistas:
            continue
        vistas.add((titulo, origem))
        referencias.append(ReferenciaFonte(titulo=titulo, origem=origem))

    if not referencias:
        # Keep the synthesized text as a single source rather than failing the
        # whole pipeline over an empty citations list - but say so, otherwise a
        # search that stopped grounding is indistinguishable from a good one.
        logger.warning(
            "Busca de fontes sem grounding_chunks para o tema %r - o texto foi salvo "
            "sem nenhuma fonte citada.",
            tema_titulo,
        )

    return [
        FonteEncontrada(
            titulo=f"Busca automática: {tema_titulo}",
            origem=None,
            conteudo=texto,
            referencias=tuple(referencias),
        )
    ]
