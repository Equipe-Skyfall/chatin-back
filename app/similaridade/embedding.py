"""Word2Vec embeddings for the duplicate-trilha check.

A text becomes the mean of its words' vectors (words the model doesn't know are
skipped). Only a pre-trained Portuguese model makes sense here - a trilha
catalogue is far too small to train one - so the model file (NILC `cbow_s50`,
word2vec text format, or a gensim `.kv`) is configured by `W2V_MODEL_PATH`.
"""

import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    dim: int

    def vetor(self, texto: str) -> list[float] | None:
        """Unit-length vector for `texto`, or None if no word of it is known."""


def _sem_acento(palavra: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", palavra) if not unicodedata.combining(c))


class Word2VecEmbedder:
    def __init__(self, keyed_vectors) -> None:
        self._kv = keyed_vectors
        self.dim = int(keyed_vectors.vector_size)

    @classmethod
    def carregar(cls, caminho: str, limite: int) -> "Word2VecEmbedder":
        from gensim.models import KeyedVectors

        if caminho.endswith(".kv"):
            kv = KeyedVectors.load(caminho)
        else:
            kv = KeyedVectors.load_word2vec_format(
                caminho, binary=caminho.endswith(".bin"), limit=limite
            )
        return cls(kv)

    def _vetor_palavra(self, palavra: str):
        for candidata in (palavra, _sem_acento(palavra)):
            if candidata in self._kv.key_to_index:
                return self._kv[candidata]
        return None

    def vetor(self, texto: str) -> list[float] | None:
        vetores = [
            v
            for v in (self._vetor_palavra(p) for p in _TOKEN.findall(texto.lower()))
            if v is not None
        ]
        if not vetores:
            return None
        media = np.mean(vetores, axis=0)
        norma = float(np.linalg.norm(media))
        if norma == 0.0:
            return None
        return (media / norma).astype(float).tolist()


@lru_cache
def get_embedder() -> Embedder | None:
    """The process-wide embedder, or None when no model is configured/readable -
    the duplicate check is then skipped instead of failing trilha creation."""
    settings = get_settings()
    caminho = settings.W2V_MODEL_PATH
    if not caminho or not Path(caminho).is_file():
        logger.warning("Modelo Word2Vec indisponível (W2V_MODEL_PATH); sem checagem de duplicatas.")
        return None
    try:
        return Word2VecEmbedder.carregar(caminho, settings.W2V_VOCAB_LIMIT)
    except Exception:  # noqa: BLE001 - a broken model file must not take creation down
        logger.warning("Falha ao carregar o modelo Word2Vec.", exc_info=True)
        return None
