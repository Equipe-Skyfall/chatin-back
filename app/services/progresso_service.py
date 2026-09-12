"""Two-level lock/unlock + best-score logic.

Progress is stored ONLY at módulo granularity (`progresso_usuario`); tema-level
and matéria-level state are always computed here by rolling módulos up - never
separately persisted, so the levels can't drift out of sync with each other.
"""

import uuid

from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.modulo import Modulo
from app.models.progresso import STATUS_CONCLUIDO, ProgressoUsuario
from app.models.tema import STATUS_PRONTO as TEMA_STATUS_PRONTO
from app.models.tema import Tema
from app.repositories.progresso_repository import ProgressoRepository
from app.repositories.xp_repository import XpRepository
from app.schemas.common import EstadoProgresso
from app.schemas.progresso import (
    ProgressoMateriaOut,
    ProgressoModuloOut,
    ProgressoOut,
    ProgressoTemaOut,
)
from app.schemas.trilha import TrilhaMateriaOut, TrilhaModuloOut, TrilhaOut, TrilhaTemaOut
from app.services import xp_service


def _modulo_concluido(progresso: ProgressoUsuario | None) -> bool:
    return progresso is not None and progresso.status == STATUS_CONCLUIDO


def _estados_modulos(
    modulos: list[Modulo], progresso_map: dict[uuid.UUID, ProgressoUsuario], tema_liberado: bool
) -> list[tuple[Modulo, EstadoProgresso]]:
    if not tema_liberado:
        return [(m, "bloqueado") for m in modulos]

    resultados: list[tuple[Modulo, EstadoProgresso]] = []
    anterior_liberado_ou_concluido = (
        True  # first módulo is always available once the tema is liberado
    )
    for modulo in modulos:
        concluido = _modulo_concluido(progresso_map.get(modulo.id))
        if anterior_liberado_ou_concluido:
            estado: EstadoProgresso = "concluido" if concluido else "disponivel"
        else:
            estado = "bloqueado"
        resultados.append((modulo, estado))
        anterior_liberado_ou_concluido = concluido
    return resultados


def _prontos(items: list, status_pronto: str) -> list:
    return sorted((i for i in items if i.status == status_pronto), key=lambda i: i.ordem)


def montar_trilha(materias: list[Materia], progresso_rows: list[ProgressoUsuario]) -> TrilhaOut:
    progresso_map = {p.modulo_id: p for p in progresso_rows}
    materias_out: list[TrilhaMateriaOut] = []

    for materia in sorted(materias, key=lambda m: m.nome):
        temas_prontos = _prontos(materia.temas, TEMA_STATUS_PRONTO)
        temas_out: list[TrilhaTemaOut] = []
        tema_anterior_concluido = True  # first tema in a matéria is always available

        for tema in temas_prontos:
            tema_liberado = tema_anterior_concluido
            modulos_prontos = _prontos(tema.modulos, MODULO_STATUS_PRONTO)
            estados_modulos = _estados_modulos(modulos_prontos, progresso_map, tema_liberado)
            tema_concluido = bool(modulos_prontos) and all(
                e == "concluido" for _, e in estados_modulos
            )
            tema_estado: EstadoProgresso = (
                "concluido" if tema_concluido else ("disponivel" if tema_liberado else "bloqueado")
            )
            temas_out.append(
                TrilhaTemaOut(
                    id=tema.id,
                    titulo=tema.titulo,
                    ordem=tema.ordem,
                    estado=tema_estado,
                    modulos=[
                        TrilhaModuloOut(id=m.id, titulo=m.titulo, ordem=m.ordem, estado=e)
                        for m, e in estados_modulos
                    ],
                )
            )
            tema_anterior_concluido = tema_concluido

        materias_out.append(
            TrilhaMateriaOut(id=materia.id, nome=materia.nome, temas=temas_out)
        )

    return TrilhaOut(materias=materias_out)


def montar_progresso(
    materias: list[Materia],
    progresso_rows: list[ProgressoUsuario],
    xp_por_materia: dict[uuid.UUID, int],
) -> ProgressoOut:
    progresso_map = {p.modulo_id: p for p in progresso_rows}
    materias_out: list[ProgressoMateriaOut] = []

    for materia in sorted(materias, key=lambda m: m.nome):
        temas_prontos = _prontos(materia.temas, TEMA_STATUS_PRONTO)
        temas_out: list[ProgressoTemaOut] = []
        tema_anterior_concluido = True

        for tema in temas_prontos:
            tema_liberado = tema_anterior_concluido
            modulos_prontos = _prontos(tema.modulos, MODULO_STATUS_PRONTO)
            estados_modulos = _estados_modulos(modulos_prontos, progresso_map, tema_liberado)
            concluidos = sum(1 for _, e in estados_modulos if e == "concluido")
            percentual_tema = (concluidos / len(modulos_prontos) * 100) if modulos_prontos else 0.0
            tema_concluido = bool(modulos_prontos) and concluidos == len(modulos_prontos)
            tema_estado: EstadoProgresso = (
                "concluido" if tema_concluido else ("disponivel" if tema_liberado else "bloqueado")
            )

            modulos_out = []
            for modulo, estado in estados_modulos:
                progresso = progresso_map.get(modulo.id)
                modulos_out.append(
                    ProgressoModuloOut(
                        modulo_id=modulo.id,
                        titulo=modulo.titulo,
                        estado=estado,
                        melhor_pontuacao=float(progresso.melhor_pontuacao)
                        if progresso and progresso.melhor_pontuacao is not None
                        else None,
                        tentativas_count=progresso.tentativas_count if progresso else 0,
                    )
                )

            temas_out.append(
                ProgressoTemaOut(
                    tema_id=tema.id,
                    titulo=tema.titulo,
                    estado=tema_estado,
                    percentual_completo=round(percentual_tema, 2),
                    modulos=modulos_out,
                )
            )
            tema_anterior_concluido = tema_concluido

        temas_concluidos = sum(1 for t in temas_out if t.estado == "concluido")
        percentual_materia = (temas_concluidos / len(temas_out) * 100) if temas_out else 0.0
        materia_concluida = bool(temas_out) and temas_concluidos == len(temas_out)
        materia_estado: EstadoProgresso = "concluido" if materia_concluida else "disponivel"

        materias_out.append(
            ProgressoMateriaOut(
                materia_id=materia.id,
                nome=materia.nome,
                estado=materia_estado,
                percentual_completo=round(percentual_materia, 2),
                xp=xp_por_materia.get(materia.id, 0),
                temas=temas_out,
            )
        )

    return ProgressoOut(materias=materias_out)


def estado_tema(
    tema: Tema, temas_da_materia: list[Tema], progresso_map: dict[uuid.UUID, ProgressoUsuario]
) -> EstadoProgresso:
    """Single-tema lock check, used by `GET /temas/{id}` to decide whether to 403."""
    temas_prontos = _prontos(temas_da_materia, TEMA_STATUS_PRONTO)
    tema_liberado = True
    for t in temas_prontos:
        modulos_prontos = _prontos(t.modulos, MODULO_STATUS_PRONTO)
        estados = _estados_modulos(modulos_prontos, progresso_map, tema_liberado)
        concluido = bool(modulos_prontos) and all(e == "concluido" for _, e in estados)
        if t.id == tema.id:
            return "concluido" if concluido else ("disponivel" if tema_liberado else "bloqueado")
        tema_liberado = concluido
    return "bloqueado"


def modulos_do_tema_com_estado(
    tema: Tema, progresso_map: dict[uuid.UUID, ProgressoUsuario]
) -> list[tuple[Modulo, EstadoProgresso]]:
    """Público, para `GET /temas/{id}`: assumes the tema itself was already
    confirmed not-bloqueado by the caller (via `estado_tema`)."""
    modulos_prontos = _prontos(tema.modulos, MODULO_STATUS_PRONTO)
    return _estados_modulos(modulos_prontos, progresso_map, tema_liberado=True)


def estado_modulo(
    modulo: Modulo,
    modulos_do_tema: list[Modulo],
    tema_estado: EstadoProgresso,
    progresso_map: dict[uuid.UUID, ProgressoUsuario],
) -> EstadoProgresso:
    """Single-módulo lock check, used by `GET /modulos/{id}` and `POST /modulos/{id}/tentativas`."""
    if tema_estado == "bloqueado":
        return "bloqueado"
    modulos_prontos = _prontos(modulos_do_tema, MODULO_STATUS_PRONTO)
    estados = _estados_modulos(modulos_prontos, progresso_map, tema_liberado=True)
    for m, estado in estados:
        if m.id == modulo.id:
            return estado
    return "bloqueado"


def atualizar_progresso(
    progresso_repo: ProgressoRepository,
    user_id: str,
    modulo_id: uuid.UUID,
    materia_id: uuid.UUID,
    pontuacao: float,
    limite_aprovacao: float,
    xp_repo: XpRepository,
) -> ProgressoUsuario:
    """Also grants XP for this attempt (see `xp_service`) - this is the one
    place a módulo's completion/retake is already detected, so XP-granting
    lives here rather than being re-derived elsewhere."""
    progresso = progresso_repo.get_or_create(user_id, modulo_id)
    era_primeira_tentativa = progresso.tentativas_count == 0
    melhor_pontuacao_anterior = (
        float(progresso.melhor_pontuacao) if progresso.melhor_pontuacao is not None else 0.0
    )

    progresso.tentativas_count += 1
    if progresso.melhor_pontuacao is None or pontuacao > float(progresso.melhor_pontuacao):
        progresso.melhor_pontuacao = pontuacao
    if pontuacao >= limite_aprovacao:
        progresso.status = STATUS_CONCLUIDO
    progresso_repo.add(progresso)

    # Every attempt after the first only earns XP for beating the previous
    # best - regardless of whether that previous attempt had already passed,
    # since the tiered first-attempt reward (see `xp_service`) already covers
    # pass-or-fail on attempt #1.
    melhoria = 0.0 if era_primeira_tentativa else max(0.0, pontuacao - melhor_pontuacao_anterior)
    xp_service.registrar_xp_por_tentativa(
        user_id,
        materia_id,
        modulo_id,
        pontuacao,
        limite_aprovacao,
        era_primeira_tentativa,
        melhoria,
        xp_repo,
    )

    return progresso
