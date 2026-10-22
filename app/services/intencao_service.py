"""Intent classification for short chat messages, without calling an LLM.

A few example phrases per intent (and some messages that are *not* an intent) are
turned into TF-IDF vectors over words and bigrams, so "o que estudar" differs
from "estudar o que" and "não quero ver" from "quero ver". Two ways to label a
message are available:

- `regressao` (the default): a logistic regression learns which words and
  pairs of words tell the intents apart, so filler shared by all of them
  ("eu estou", "quero ver") weighs little. It also learns a "nenhuma" class
  from the negative messages.
- `cosseno`: the label of the example the message is closest to, by cosine
  similarity. Simpler, but it is misled by the filler words.

Either way it is deliberately conservative: a message the classifier is not
sure about, one with a negation or two requests in one, or one with too many
words the examples never use, gets `None` and goes to the agent as usual - a
missed shortcut costs one normal turn, a wrong one would answer the wrong
thing. `avaliar` scores a labelled set of messages (precision and recall per
intent), which is how the examples and the thresholds are tuned.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

INTENCAO_DESEMPENHO = "desempenho"
INTENCAO_PROXIMOS_ESTUDOS = "proximos_estudos"
INTENCAO_XP = "xp"
INTENCAO_RANKING = "ranking"

EXEMPLOS: dict[str, list[str]] = {
    INTENCAO_DESEMPENHO: [
        "como estou indo",
        "como tô indo nos estudos",
        "estou indo bem",
        "como está meu desempenho",
        "meu desempenho",
        "qual é o meu desempenho",
        "quero ver meu desempenho",
        "mostra meu desempenho",
        "como está minha performance",
        "meu rendimento nos estudos",
        "como estou nos estudos",
        "quanto eu acertei",
        "quantas questões eu acertei",
        "minha taxa de acerto",
        "qual minha média de acertos",
        "quero ver minhas notas",
        "como estão minhas notas",
        "meu progresso",
        "como está meu progresso",
        "como anda meu progresso nas matérias",
        "em que temas estou melhor",
        "em quais temas tenho dificuldade",
        "quais são meus pontos fracos",
        "em que estou fraco",
        "onde eu mais erro",
        "quais são meus pontos fortes",
        "como eu to indo na matéria",
        "me fala como está meu desempenho",
        "quero saber minha porcentagem de acerto",
        "eu estou evoluindo",
        "quais temas eu domino",
        "onde estou errando mais",
        "meu resultado nas provas",
        "como foi meu aproveitamento",
        "qual meu índice de acerto",
        "estou me saindo bem",
        "me mostra como estou",
        "como está minha evolução",
        "meu histórico de acertos e erros",
        "quero um balanço dos meus estudos",
        "estou melhorando",
        "como foi minha última prova",
    ],
    INTENCAO_PROXIMOS_ESTUDOS: [
        "o que estudar",
        "o que estudar hoje",
        "o que devo estudar agora",
        "o que eu estudo hoje",
        "o que tem para estudar",
        "por onde continuar",
        "por onde começo",
        "por onde começo a estudar",
        "qual é o próximo módulo",
        "qual o próximo assunto",
        "qual o próximo conteúdo",
        "o que vem depois",
        "o que revisar",
        "o que preciso revisar",
        "o que devo revisar hoje",
        "me recomende o que estudar",
        "me sugira o que estudar",
        "preciso de uma recomendação de estudo",
        "qual conteúdo estudar em seguida",
        "qual conteúdo devo ver agora",
        "qual matéria estudar agora",
        "o que fazer agora nos estudos",
        "o que devo ver hoje",
        "qual é o próximo passo nos estudos",
        "me diz o que estudar agora",
        "qual assunto eu devo estudar primeiro",
        "o que eu faço agora",
        "qual o melhor conteúdo para eu estudar",
        "o que está pendente para mim",
        "tem algum módulo para eu revisar",
        "sugira um módulo para hoje",
        "qual lição eu devo fazer agora",
        "onde eu continuo meus estudos",
        "me indica o que estudar",
        "o que falta eu estudar",
        "qual tema devo estudar agora",
        "o que está liberado para estudar",
        "me ajuda a escolher o que estudar",
    ],
    INTENCAO_XP: [
        "quanto xp eu tenho",
        "quantos xp eu tenho",
        "meu xp",
        "qual é o meu xp",
        "quantos pontos de xp eu tenho",
        "quantos pontos de experiência eu tenho",
        "qual é o meu nível",
        "em que nível estou",
        "meu nível",
        "meu level",
        "em qual level estou",
        "quanto falta para o próximo nível",
        "falta muito para o próximo nível",
        "quanto xp falta para subir de nível",
        "quanto xp preciso para o nível seguinte",
        "quanto xp ganhei",
        "quantos pontos eu tenho",
        "qual é meu total de xp",
        "quanto falta para eu subir de nível",
        "em que nível eu tô",
        "me fala meu nível atual",
        "quantos xp faltam para o próximo nível",
        "minha experiência total",
        "já passei de nível",
        "qual meu saldo de xp",
        "quanto xp eu já acumulei",
        "quando eu subo de nível",
        "qual meu nível de experiência",
    ],
    INTENCAO_RANKING: [
        "qual minha posição no ranking",
        "qual é a minha posição",
        "em que posição estou",
        "meu lugar no ranking",
        "em que lugar estou no ranking",
        "quem está em primeiro no ranking",
        "quem lidera o ranking",
        "quem está no topo",
        "quem tem mais xp",
        "ver o ranking",
        "mostre o ranking",
        "qual o ranking",
        "ranking geral",
        "ver a classificação geral",
        "mostra a classificação",
        "estou bem colocado no ranking",
        "quem são os primeiros do ranking",
        "quem são os melhores alunos",
        "qual minha colocação",
        "quem está ganhando no ranking",
        "estou entre os primeiros",
        "me mostra o ranking de xp",
        "quem é o líder",
        "qual a minha classificação entre os alunos",
        "ver os melhores colocados",
        "quem está na frente",
        "qual a minha colocação no ranking geral",
        "quem são os líderes do ranking",
        "estou no topo do ranking",
        "quantos alunos estão na minha frente",
    ],
}

# Messages that are NOT one of the requests above, so the classifier also learns
# what to leave to the agent: subject questions that reuse the same words,
# other requests and smalltalk.
NEGATIVOS: list[str] = [
    "o que é desempenho em física?",
    "explique a revolução francesa",
    "como melhorar meu desempenho em redação",
    "quanto é 15 por cento de 80",
    "o que significa nível do mar",
    "qual a posição do sol ao meio dia",
    "me explique o que é xp em jogos",
    "oi",
    "obrigado",
    "tudo bem?",
    "como calcular a média de um conjunto de dados",
    "o que é nível de significância",
    "explique o que é desempenho em uma empresa",
    "qual é o próximo número da sequência 2 4 8",
    "como estudar melhor para a prova",
    "quem foi o primeiro imperador do brasil",
    "qual a classificação dos seres vivos",
    "o que é xp em jogos de rpg",
    "quero estudar história",
    "me recomenda um livro de física",
    "quanto é a raiz de 144",
    "onde fica a posição do ponto no gráfico",
    "pode me ajudar com uma redação",
    "bom dia",
    "valeu",
    "explique funções do segundo grau",
    "qual o desempenho de um motor a combustão",
    "explique a lei de newton",
    "quais foram as causas da primeira guerra",
    "como estudar matemática de forma eficiente",
    "o que significa a palavra efêmero",
    "quem descobriu o brasil",
    "o que é o nível freático",
    "qual é a posição de um vetor no plano",
    "quero um resumo sobre fotossíntese",
    "me ajuda a estudar para o enem",
    "como faço uma redação nota mil",
    "o ranking das maiores economias do mundo",
    "quanto é dois mais dois",
    "boa tarde tudo bem",
    "obrigada pela ajuda",
    "me explica o que é progressão aritmética",
    "quais são os pontos fortes do iluminismo",
]

# Only the filler words: question words and possessives ("o que", "meu", "como")
# are what tell the intents apart.
STOPWORDS = ["a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na"]

# Cosine similarity ignores words the examples never use, so a longer message
# that merely contains an example scores high ("não quero ver meu desempenho").
# Two guards cover that: a negation turns the request around, and at least
# `COBERTURA` of the message's words must be ones the examples know.
NEGACOES = {"nao", "nunca", "jamais", "sem", "nenhum", "nenhuma"}
# Two requests in one message ("meu xp e meu ranking"): the agent can answer both.
CONJUNCOES = re.compile(r"\b(e|ou|tambem|alem)\b")

METODO_PADRAO = "regressao"
Metodo = Literal["regressao", "cosseno"]
# Minimum probability (regressao) or cosine similarity (cosseno) to take a shortcut.
LIMIARES: dict[str, float] = {"regressao": 0.7, "cosseno": 0.4}
MARGEM_COSSENO = 0.1
COBERTURA = 0.7
NGRAMAS = (1, 2)
FORCA_REGRESSAO = 30.0  # inverse regularization (`C`) of the logistic regression
ROTULO_NENHUMA = "nenhuma"


def _sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


@dataclass(frozen=True)
class Classificacao:
    intencao: str
    pontuacao: float


class ClassificadorDeIntencao:
    def __init__(
        self,
        exemplos: dict[str, list[str]] | None = None,
        negativos: list[str] | None = None,
        metodo: Metodo = METODO_PADRAO,
        limiar: float | None = None,
        margem: float | None = None,
        cobertura: float = COBERTURA,
        ngramas: tuple[int, int] = NGRAMAS,
    ):
        if exemplos is None:
            exemplos = EXEMPLOS
            negativos = NEGATIVOS if negativos is None else negativos
        negativos = negativos or []
        self._metodo = metodo
        self._limiar = LIMIARES[metodo] if limiar is None else limiar
        self._margem = (
            (MARGEM_COSSENO if metodo == "cosseno" else 0.0) if margem is None else margem
        )
        self._cobertura = cobertura
        self._rotulos = [r for r, frases in exemplos.items() for _ in frases]
        textos = [f for frases in exemplos.values() for f in frases]
        self._rotulos += [ROTULO_NENHUMA] * len(negativos)
        textos_todos = textos + negativos
        self._vetorizador = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            ngram_range=ngramas,
            stop_words=STOPWORDS,
            sublinear_tf=True,
        )
        self._matriz = self._vetorizador.fit_transform(textos_todos)
        self._modelo = (
            LogisticRegression(C=FORCA_REGRESSAO, max_iter=2000).fit(self._matriz, self._rotulos)
            if metodo == "regressao"
            else None
        )
        # Words only (no bigrams), to measure how much of a message the intent
        # examples cover; the negatives are not part of that vocabulary.
        self._palavras = TfidfVectorizer(
            lowercase=True, strip_accents="unicode", stop_words=STOPWORDS
        ).build_analyzer()
        self._vocabulario = {palavra for texto in textos for palavra in self._palavras(texto)}

    def _cobertura_da_mensagem(self, palavras: list[str]) -> float:
        if not palavras:
            return 0.0
        return sum(p in self._vocabulario for p in palavras) / len(palavras)

    def pontuacoes(self, mensagem: str) -> dict[str, float]:
        """Per label (the intents and "nenhuma"): the probability (regressao) or
        the best cosine similarity to one of its examples (cosseno)."""
        vetor = self._vetorizador.transform([mensagem])
        if self._modelo is not None:
            probabilidades = self._modelo.predict_proba(vetor)[0]
            return {r: float(p) for r, p in zip(self._modelo.classes_, probabilidades, strict=True)}
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
        if CONJUNCOES.search(_sem_acentos(mensagem.lower())):
            return None
        if self._cobertura_da_mensagem(palavras) < self._cobertura:
            return None
        ordenadas = sorted(self.pontuacoes(mensagem).items(), key=lambda p: p[1], reverse=True)
        melhor_rotulo, melhor = ordenadas[0]
        segunda = ordenadas[1][1] if len(ordenadas) > 1 else 0.0
        if melhor_rotulo == ROTULO_NENHUMA:
            return None
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
