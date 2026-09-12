"""Question difficulty is computed from real student performance (the
fraction of recorded answers that were wrong) - never assigned by the AI at
generation time. A question needs a minimum number of recorded answers
before its computed difficulty is trusted; below that (including a brand-new
question with zero attempts) it's treated as "médio", the cold-start default.

Also home to the adaptive-selection weighting used by
`grading_service.iniciar_tentativa`: a student's general skill signal (their
average score across every attempt they've ever completed) shifts the sample
toward harder questions when they're doing well, and toward easier ones when
they're struggling.
"""

import random
import uuid
from collections.abc import Iterable

FACIL = "facil"
MEDIO = "medio"
DIFICIL = "dificil"

MINIMO_RESPOSTAS_PARA_CONFIAR = 10

NIVEL_INDO_BEM = "indo_bem"
NIVEL_NEUTRO = "neutro"
NIVEL_COM_DIFICULDADE = "com_dificuldade"

PESOS_POR_NIVEL: dict[str, dict[str, float]] = {
    NIVEL_INDO_BEM: {FACIL: 1.0, MEDIO: 2.0, DIFICIL: 4.0},
    NIVEL_NEUTRO: {FACIL: 1.0, MEDIO: 1.0, DIFICIL: 1.0},
    NIVEL_COM_DIFICULDADE: {FACIL: 4.0, MEDIO: 2.0, DIFICIL: 1.0},
}


def classificar(taxa_erro: float) -> str:
    if taxa_erro < 0.35:
        return FACIL
    if taxa_erro < 0.65:
        return MEDIO
    return DIFICIL


def dificuldade_por_questao(
    questao_ids: list[uuid.UUID], questionario_repo
) -> dict[uuid.UUID, str]:
    estatisticas = questionario_repo.estatisticas_por_questao(questao_ids)
    resultado = {}
    for qid in questao_ids:
        total, taxa_erro = estatisticas.get(qid, (0, 0.0))
        resultado[qid] = classificar(taxa_erro) if total >= MINIMO_RESPOSTAS_PARA_CONFIAR else MEDIO
    return resultado


def nivel_do_aluno(media_pontuacao: float | None) -> str:
    if media_pontuacao is None:
        return NIVEL_NEUTRO
    if media_pontuacao >= 80:
        return NIVEL_INDO_BEM
    if media_pontuacao < 50:
        return NIVEL_COM_DIFICULDADE
    return NIVEL_NEUTRO


def amostra_ponderada_sem_reposicao(
    itens: Iterable[uuid.UUID], pesos: dict[uuid.UUID, float], k: int
) -> list[uuid.UUID]:
    """Weighted sampling without replacement (Efraimidis-Spirakis): give each
    item a random key raised to 1/weight, keep the top-k keys. Plain
    `random.sample`/`random.choices` don't cover "weighted, no duplicates",
    and pulling in numpy for this one algorithm isn't worth a new dependency.
    """
    chaves = [
        (random.random() ** (1.0 / max(pesos.get(item, 1.0), 1e-6)), item) for item in itens
    ]
    chaves.sort(key=lambda par: par[0], reverse=True)
    return [item for _, item in chaves[:k]]
