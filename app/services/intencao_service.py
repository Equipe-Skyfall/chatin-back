"""Intent classification for short chat messages, without calling an LLM.

A handful of example phrases per intent are turned into TF-IDF vectors (a
bag of words and bigrams, so "o que estudar" differs from "estudar o que" and
"não quero ver" from "quero ver"). A message gets the label of the intent whose
examples it is closest to, by cosine similarity. It is deliberately
conservative: below `LIMIAR` of similarity, or when two intents are nearly
tied, it answers `None` and the message goes to the agent as usual - a missed
shortcut costs one normal turn, a wrong one would answer the wrong thing.

Pure and fast (a few dozen examples), so the classifier is built once and
reused. `avaliar` scores a labelled set of messages (precision and recall per
intent), which is how the examples and the threshold are tuned.
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

INTENCAO_DESEMPENHO = "desempenho"
INTENCAO_PROXIMOS_ESTUDOS = "proximos_estudos"
INTENCAO_XP = "xp"
INTENCAO_RANKING = "ranking"

EXEMPLOS: dict[str, list[str]] = {
    INTENCAO_DESEMPENHO: [
        "como estou indo",
        "como está meu desempenho",
        "meu desempenho",
        "qual é o meu desempenho",
        "quero ver meu desempenho",
        "como estou nos estudos",
        "quanto eu acertei",
        "minha taxa de acerto",
        "meu progresso",
        "como está meu progresso",
        "em que temas estou melhor",
        "em quais temas tenho dificuldade",
    ],
    INTENCAO_PROXIMOS_ESTUDOS: [
        "o que estudar",
        "o que devo estudar agora",
        "o que eu estudo hoje",
        "por onde continuar",
        "por onde começo",
        "qual é o próximo módulo",
        "o que revisar",
        "o que preciso revisar",
        "me recomende o que estudar",
        "qual conteúdo estudar em seguida",
    ],
    INTENCAO_XP: [
        "quanto xp eu tenho",
        "meu xp",
        "quantos pontos de xp eu tenho",
        "qual é o meu nível",
        "em que nível estou",
        "quanto falta para o próximo nível",
        "quanto xp falta para subir de nível",
    ],
    INTENCAO_RANKING: [
        "qual minha posição no ranking",
        "meu lugar no ranking",
        "quem está em primeiro no ranking",
        "ver o ranking",
        "mostre o ranking",
        "estou bem colocado no ranking",
        "quem está liderando o ranking",
        "quem são os primeiros do ranking",
    ],
}

# Only the filler words: question words and possessives ("o que", "meu", "como")
# are what tell the intents apart.
STOPWORDS = ["a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na"]

# Cosine similarity ignores words the examples never use, so a longer message
# that merely contains an example scores high ("não quero ver meu desempenho").
# Two guards cover that: a negation turns the request around, and at least
# `COBERTURA` of the message's words must be ones the examples know.
NEGACOES = {"nao", "nunca", "jamais", "sem", "nenhum", "nenhuma"}

LIMIAR = 0.5
MARGEM = 0.1
COBERTURA = 0.75
NGRAMAS = (1, 2)


@dataclass(frozen=True)
class Classificacao:
    intencao: str
    pontuacao: float


class ClassificadorDeIntencao:
    def __init__(
        self,
        exemplos: dict[str, list[str]] | None = None,
        limiar: float = LIMIAR,
        margem: float = MARGEM,
        cobertura: float = COBERTURA,
        ngramas: tuple[int, int] = NGRAMAS,
    ):
        exemplos = exemplos or EXEMPLOS
        self._rotulos = [r for r, frases in exemplos.items() for _ in frases]
        textos = [f for frases in exemplos.values() for f in frases]
        self._limiar = limiar
        self._margem = margem
        self._cobertura = cobertura
        self._vetorizador = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            ngram_range=ngramas,
            stop_words=STOPWORDS,
            sublinear_tf=True,
        )
        self._matriz = self._vetorizador.fit_transform(textos)
        # Words only (no bigrams), to measure how much of a message the examples cover.
        self._palavras = TfidfVectorizer(
            lowercase=True, strip_accents="unicode", stop_words=STOPWORDS
        ).build_analyzer()
        self._vocabulario = {palavra for texto in textos for palavra in self._palavras(texto)}

    def _cobertura_da_mensagem(self, palavras: list[str]) -> float:
        if not palavras:
            return 0.0
        return sum(p in self._vocabulario for p in palavras) / len(palavras)

    def pontuacoes(self, mensagem: str) -> dict[str, float]:
        """The best similarity to any example of each intent."""
        vetor = self._vetorizador.transform([mensagem])
        similaridades = cosine_similarity(vetor, self._matriz)[0]
        melhores: dict[str, float] = {}
        for rotulo, similaridade in zip(self._rotulos, similaridades, strict=True):
            melhores[rotulo] = max(melhores.get(rotulo, 0.0), float(similaridade))
        return melhores

    def classificar(self, mensagem: str) -> Classificacao | None:
        if not mensagem or not mensagem.strip():
            return None
        palavras = self._palavras(mensagem)
        if any(p in NEGACOES for p in palavras):
            return None
        if self._cobertura_da_mensagem(palavras) < self._cobertura:
            return None
        ordenadas = sorted(self.pontuacoes(mensagem).items(), key=lambda p: p[1], reverse=True)
        melhor_rotulo, melhor = ordenadas[0]
        segunda = ordenadas[1][1] if len(ordenadas) > 1 else 0.0
        if melhor < self._limiar or melhor - segunda < self._margem:
            return None
        return Classificacao(intencao=melhor_rotulo, pontuacao=round(melhor, 4))


@lru_cache(maxsize=1)
def classificador_padrao() -> ClassificadorDeIntencao:
    return ClassificadorDeIntencao()


def classificar_intencao(mensagem: str) -> Classificacao | None:
    return classificador_padrao().classificar(mensagem)


def avaliar(
    casos: list[tuple[str, str | None]], classificador: ClassificadorDeIntencao
) -> dict[str, dict[str, float]]:
    """Precision and recall per intent over `(message, expected intent or None)`
    pairs, where `None` means "must go to the agent". Precision is the share of
    shortcuts taken that were right; recall the share of messages that should
    have been shortcut and were."""
    verdadeiros: Counter[str] = Counter()
    previstos: Counter[str] = Counter()
    esperados: Counter[str] = Counter()
    for mensagem, esperado in casos:
        resultado = classificador.classificar(mensagem)
        previsto = resultado.intencao if resultado else None
        if previsto is not None:
            previstos[previsto] += 1
        if esperado is not None:
            esperados[esperado] += 1
        if previsto is not None and previsto == esperado:
            verdadeiros[previsto] += 1
    intencoes = sorted(set(previstos) | set(esperados))
    return {
        intencao: {
            "precisao": verdadeiros[intencao] / previstos[intencao] if previstos[intencao] else 1.0,
            "recall": verdadeiros[intencao] / esperados[intencao] if esperados[intencao] else 1.0,
        }
        for intencao in intencoes
    }
