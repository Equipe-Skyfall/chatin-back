"""Which módulo the student should study next (US-9).

Every módulo the student can open gets a priority and the highest wins:

- never studied: a fixed medium-high priority, so new content is not ignored
  but a weak or overdue módulo still comes first;
- studied before: how weak the tema is (`1 - taxa de acerto`) plus how overdue
  the review is. The review interval is the spaced-repetition part - a weak tema
  is due again after a day, a strong one only after a week - and the time
  component grows linearly with the days since the last study, up to twice
  that interval, so a long-neglected review eventually outranks new content.

The tema's hit rate comes from every answer in completed quizzes (the same
number `/progresso` shows as `desempenho`); until there are enough answers to
trust it the tema counts as "médio". Pure functions over `ProgressoOut`, so
the rules are testable without a database.
"""

import uuid
from datetime import UTC, datetime

from app.schemas.progresso import ProgressoModuloOut, ProgressoOut, ProgressoTemaOut
from app.schemas.recomendacao import RecomendacaoOut
from app.services import dificuldade_service

PRIORIDADE_NAO_ESTUDADO = 0.55
PESO_DESEMPENHO = 0.6
PESO_TEMPO = 0.4

# Days until a módulo is due for review again, by the student's level in its tema.
INTERVALO_REVISAO_DIAS = {
    dificuldade_service.DESEMPENHO_BAIXO: 1.0,
    dificuldade_service.DESEMPENHO_MEDIO: 3.0,
    dificuldade_service.DESEMPENHO_ALTO: 7.0,
}

# How many review intervals of lateness still raise the priority. Past 1 the
# módulo is overdue; the headroom lets a long-neglected review (even of a strong
# tema) eventually outrank brand-new content.
ATRASO_MAXIMO = 2.0

# Hit rate assumed for a tema without enough answers to trust.
TAXA_ACERTO_NEUTRA = 0.5


def _estudado(modulo: ProgressoModuloOut, ultimo_estudo: datetime | None) -> bool:
    return ultimo_estudo is not None or modulo.tentativas_count > 0 or modulo.estado == "concluido"


def _taxa_acerto(tema: ProgressoTemaOut) -> float:
    if tema.desempenho.total_respostas < dificuldade_service.MINIMO_RESPOSTAS_PARA_NIVEL_TEMA:
        return TAXA_ACERTO_NEUTRA
    return tema.desempenho.taxa_acerto / 100


def _dias_desde(ultimo_estudo: datetime | None, agora: datetime, intervalo: float) -> float:
    """A módulo marked done with no recorded attempt (older data) counts as
    due, since there is no date to measure from."""
    if ultimo_estudo is None:
        return intervalo
    return max((agora - ultimo_estudo).total_seconds() / 86400, 0.0)


def _justificativa_estudado(
    motivo: str, tema: ProgressoTemaOut, taxa: float, dias: int | None
) -> str:
    if motivo == "baixo_desempenho":
        return (
            f"Seu desempenho em {tema.titulo} está em {round(taxa * 100)}% de acerto; "
            "vale reforçar esse conteúdo."
        )
    quando = "há algum tempo" if dias is None else f"há {dias} dia(s)"
    return f"Você estudou {tema.titulo} {quando}; revisar agora ajuda a fixar o conteúdo."


def recomendar_proximo_estudo(
    progresso: ProgressoOut,
    ultimo_estudo_por_modulo: dict[uuid.UUID, datetime],
    agora: datetime | None = None,
) -> RecomendacaoOut | None:
    """The módulo to study next, or `None` when no módulo is open to the student
    (everything is locked, or there is no content yet). Ties keep the trail's
    order, so the earliest módulo wins."""
    agora = agora or datetime.now(UTC)
    melhor: tuple[float, RecomendacaoOut] | None = None

    for materia in progresso.materias:
        for tema in materia.temas:
            taxa = _taxa_acerto(tema)
            intervalo = INTERVALO_REVISAO_DIAS[tema.desempenho.nivel]
            for modulo in tema.modulos:
                if modulo.estado == "bloqueado":
                    continue
                ultimo = ultimo_estudo_por_modulo.get(modulo.modulo_id)

                if not _estudado(modulo, ultimo):
                    prioridade = PRIORIDADE_NAO_ESTUDADO
                    motivo = "nao_estudado"
                    dias = None
                    justificativa = f"Você ainda não estudou {modulo.titulo}."
                else:
                    dias_exatos = _dias_desde(ultimo, agora, intervalo)
                    dias = None if ultimo is None else int(dias_exatos)
                    desempenho = PESO_DESEMPENHO * (1 - taxa)
                    tempo = PESO_TEMPO * min(dias_exatos / intervalo, ATRASO_MAXIMO)
                    prioridade = desempenho + tempo
                    motivo = "baixo_desempenho" if desempenho >= tempo else "revisao_espacada"
                    justificativa = _justificativa_estudado(motivo, tema, taxa, dias)

                if melhor is None or prioridade > melhor[0]:
                    melhor = (
                        prioridade,
                        RecomendacaoOut(
                            modulo_id=modulo.modulo_id,
                            modulo_titulo=modulo.titulo,
                            tema_id=tema.tema_id,
                            tema_titulo=tema.titulo,
                            materia_id=materia.materia_id,
                            materia_nome=materia.nome,
                            motivo=motivo,
                            justificativa=justificativa,
                            prioridade=round(prioridade, 4),
                            ultimo_estudo=ultimo,
                            dias_desde_ultimo_estudo=dias,
                            taxa_acerto_tema=(
                                None
                                if tema.desempenho.total_respostas == 0
                                else tema.desempenho.taxa_acerto
                            ),
                        ),
                    )

    return None if melhor is None else melhor[1]
