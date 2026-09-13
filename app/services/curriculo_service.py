"""Business logic for curating the curriculum (matéria/tema/módulo/questão).

This is the single source of truth for "create a tema", "edit a questão", etc.
Both the REST routers (`app/routers/*.py`) and the admin chat agent's tools
(`app/services/agent_tools.py`) call these same functions - neither has its
own copy of this logic, so there is exactly one place that decides what
"creating a módulo" actually does.
"""

import logging
import uuid
from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError

from app.ai.base import AIProvider
from app.core.exceptions import (
    AppException,
    ConteudoIndisponivelException,
    MateriaNaoEncontradaException,
    ModuloNaoEncontradoException,
    ModulosJaExistemException,
    OrdemDuplicadaException,
    QuestaoNaoEncontradaException,
    QuestionarioNaoEncontradoException,
    TemaNaoEncontradoException,
    TemaNaoProntoException,
    TrilhaLimiteExcedidoException,
)
from app.models.materia import Materia
from app.models.modulo import STATUS_GERANDO as MODULO_STATUS_GERANDO
from app.models.modulo import Modulo
from app.models.questao import Questao
from app.models.tema import STATUS_GERANDO as TEMA_STATUS_GERANDO
from app.models.tema import STATUS_PRONTO as TEMA_STATUS_PRONTO
from app.models.tema import Tema
from app.repositories.materia_repository import MateriaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tema_repository import TemaRepository
from app.services.conteudo_modulo_pipeline import gerar_conteudo_modulo
from app.services.fonte_pipeline import buscar_fontes_tema
from app.services.questionario_pipeline import gerar_questionario_modulo

logger = logging.getLogger(__name__)

MAX_MODULOS_AUTO_SPLIT = 5


def _proxima_ordem(ordens: Iterable[int]) -> int:
    """Next free `ordem` at some level (matéria/tema/módulo) - lets callers
    (routers, the admin agent) omit `ordem` entirely for the common case of
    "just add it at the end", instead of having to know the sibling count."""
    return max(ordens, default=-1) + 1


def _commit_com_ordem(repo, ordem: int) -> None:
    """Commits and translates the DB's unique-ordem constraint into a clean
    `AppException` instead of a raw `IntegrityError` - without this, an
    explicit `ordem` that collides with a sibling crashes as an unhandled 500
    (which, worse, drops CORS headers and shows the browser client "Failed to
    fetch" instead of a readable error)."""
    try:
        repo.commit()
    except IntegrityError as exc:
        repo.rollback()
        raise OrdemDuplicadaException(ordem) from exc


# --- Matéria ---


def criar_materia(
    nome: str,
    descricao: str | None,
    materia_repo: MateriaRepository,
    *,
    owner_user_id: str | None = None,
    limite_trilhas: int | None = None,
) -> Materia:
    """Matérias have no `ordem` - they're siblings (Matemática, Física, ...),
    not a sequence. Ordering starts one level down, at tema (see `criar_tema`).

    `owner_user_id=None` (the default) creates global, admin-curated content -
    unchanged behavior. A non-`None` value creates a student's own personal
    trilha instead, capped at `limite_trilhas` (required whenever
    `owner_user_id` is set - see `Settings.TRILHAS_MAX_POR_USUARIO`)."""
    if owner_user_id is not None:
        assert limite_trilhas is not None, "limite_trilhas é obrigatório para trilha pessoal"
        if materia_repo.count_by_owner(owner_user_id) >= limite_trilhas:
            raise TrilhaLimiteExcedidoException(limite_trilhas)

    materia = Materia(nome=nome, descricao=descricao, owner_user_id=owner_user_id)
    materia_repo.add(materia)
    materia_repo.commit()
    materia_repo.refresh(materia)
    return materia


def atualizar_materia(
    materia_id: uuid.UUID,
    nome: str | None,
    descricao: str | None,
    materia_repo: MateriaRepository,
) -> Materia:
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    if nome is not None:
        materia.nome = nome
    if descricao is not None:
        materia.descricao = descricao
    materia_repo.add(materia)
    materia_repo.commit()
    materia_repo.refresh(materia)
    return materia


def deletar_materia(materia_id: uuid.UUID, materia_repo: MateriaRepository) -> None:
    materia = materia_repo.get(materia_id)
    if materia is None:
        raise MateriaNaoEncontradaException(materia_id)
    materia_repo.delete(materia)
    materia_repo.commit()


# --- Tema ---


def criar_tema(
    materia_id: uuid.UUID,
    titulo: str,
    descricao: str | None,
    materia_repo: MateriaRepository,
    tema_repo: TemaRepository,
    ai_provider: AIProvider,
    *,
    direcionamento: str | None = None,
) -> Tema:
    """Always appended after this matéria's existing temas - `ordem` isn't a
    creation-time input (see `TemaCreate`); use `atualizar_tema` to reorder
    afterward."""
    if materia_repo.get(materia_id) is None:
        raise MateriaNaoEncontradaException(materia_id)

    ordem = _proxima_ordem(t.ordem for t in tema_repo.list_by_materia(materia_id))

    tema = Tema(
        materia_id=materia_id,
        titulo=titulo,
        descricao=descricao,
        ordem=ordem,
        status=TEMA_STATUS_GERANDO,
        direcionamento=direcionamento,
    )
    tema_repo.add(tema)
    _commit_com_ordem(tema_repo, ordem)
    tema_repo.refresh(tema)

    buscar_fontes_tema(tema, tema_repo, ai_provider)
    tema_repo.refresh(tema)
    return tema


def atualizar_tema(
    materia_id: uuid.UUID,
    tema_id: uuid.UUID,
    titulo: str | None,
    descricao: str | None,
    ordem: int | None,
    tema_repo: TemaRepository,
    direcionamento: str | None = None,
) -> Tema:
    tema = tema_repo.get(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)
    if titulo is not None:
        tema.titulo = titulo
    if descricao is not None:
        tema.descricao = descricao
    if ordem is not None:
        tema.ordem = ordem
    if direcionamento is not None:
        tema.direcionamento = direcionamento
    tema_repo.add(tema)
    if ordem is not None:
        _commit_com_ordem(tema_repo, ordem)
    else:
        tema_repo.commit()
    tema_repo.refresh(tema)
    return tema


def deletar_tema(materia_id: uuid.UUID, tema_id: uuid.UUID, tema_repo: TemaRepository) -> None:
    tema = tema_repo.get(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)
    tema_repo.delete(tema)
    tema_repo.commit()


def regenerar_tema(
    materia_id: uuid.UUID, tema_id: uuid.UUID, tema_repo: TemaRepository, ai_provider: AIProvider
) -> Tema:
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None or tema.materia_id != materia_id:
        raise TemaNaoEncontradoException(tema_id)

    for fonte in list(tema.fontes):
        tema_repo.db.delete(fonte)
    tema.status = TEMA_STATUS_GERANDO
    tema_repo.add(tema)
    tema_repo.commit()
    tema_repo.refresh(tema)

    buscar_fontes_tema(tema, tema_repo, ai_provider)
    tema_repo.refresh(tema)
    return tema


# --- Módulo ---


def _conteudo_ja_coberto(
    tema: Tema, ordem_atual: int, excluir_modulo_id: uuid.UUID | None = None
) -> list[str]:
    """The actual content of every earlier módulo (lower `ordem`) under this
    tema that already has content - fed to the next módulo's generation so it
    continues instead of repeating them."""
    anteriores = sorted(
        (
            m
            for m in tema.modulos
            if m.ordem < ordem_atual and m.conteudo and m.id != excluir_modulo_id
        ),
        key=lambda m: m.ordem,
    )
    return [m.conteudo for m in anteriores]


MODELO_IA_MANUAL = "manual"


def criar_modulo(
    tema_id: uuid.UUID,
    titulo: str,
    descricao: str | None,
    pool_size: int,
    tema_repo: TemaRepository,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
    *,
    conteudo: str | None = None,
) -> Modulo:
    """Always appended after this tema's existing módulos - `ordem` isn't a
    creation-time input (see `ModuloCreate`); use `atualizar_modulo` to
    reorder afterward.

    `conteudo`: an admin can write the teaching material by hand instead of
    having the AI generate it - pass it here to skip that one AI call. The
    quiz is still AI-generated from whatever content ends up on the módulo
    (hand-written or not) - authoring 12 multiple-choice questions by hand
    isn't a capability this offers today; use the admin chat's
    `editar_questao` afterward for one-off manual corrections instead.
    """
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    if tema.status != TEMA_STATUS_PRONTO:
        raise TemaNaoProntoException()

    ordem = _proxima_ordem(m.ordem for m in tema.modulos)

    conteudo_ja_coberto = _conteudo_ja_coberto(tema, ordem)

    modulo = Modulo(
        tema_id=tema_id,
        titulo=titulo,
        descricao=descricao,
        ordem=ordem,
        status=MODULO_STATUS_GERANDO,
    )
    modulo_repo.add(modulo)
    _commit_com_ordem(modulo_repo, ordem)
    modulo_repo.refresh(modulo)

    if conteudo:
        modulo_repo.definir_conteudo(modulo, conteudo, MODELO_IA_MANUAL)
        modulo_repo.commit()
    else:
        gerar_conteudo_modulo(modulo, tema, modulo_repo, ai_provider, conteudo_ja_coberto)
    gerar_questionario_modulo(modulo, questionario_repo, modulo_repo, ai_provider, pool_size)
    modulo_repo.refresh(modulo)
    return modulo


def dividir_tema_em_modulos(
    tema_id: uuid.UUID,
    pool_size: int,
    tema_repo: TemaRepository,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
    max_modulos: int = MAX_MODULOS_AUTO_SPLIT,
) -> list[Modulo]:
    """Asks the AI to propose an outline (at most `max_modulos`) for this
    tema, then creates each módulo in order - feeding each one the actual
    content of the módulos already created before it (see
    `_conteudo_ja_coberto`) so the series reads as one continuous course
    instead of repeated introductions. Only allowed on a tema with no módulos
    yet, to keep ordering/continuity unambiguous; use the one-at-a-time
    endpoint to add more afterward (it honors continuity too)."""
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)
    if tema.status != TEMA_STATUS_PRONTO:
        raise TemaNaoProntoException()
    if tema.modulos:
        raise ModulosJaExistemException()

    plano = ai_provider.planejar_modulos(
        tema.titulo,
        tema.descricao,
        [f.conteudo_extraido for f in tema.fontes],
        max_modulos,
        tema.direcionamento,
    )

    criados: list[Modulo] = []
    for ordem, planejado in enumerate(plano.modulos):
        modulo = Modulo(
            tema_id=tema_id,
            titulo=planejado.titulo,
            descricao=planejado.descricao,
            ordem=ordem,
            status=MODULO_STATUS_GERANDO,
        )
        modulo_repo.add(modulo)
        modulo_repo.commit()
        modulo_repo.refresh(modulo)
        criados.append(modulo)

        tema_atualizado = tema_repo.get_with_relations(tema_id)
        conteudo_ja_coberto = _conteudo_ja_coberto(tema_atualizado, ordem)

        try:
            gerar_conteudo_modulo(
                modulo, tema_atualizado, modulo_repo, ai_provider, conteudo_ja_coberto
            )
            gerar_questionario_modulo(
                modulo, questionario_repo, modulo_repo, ai_provider, pool_size
            )
        except AppException as exc:
            # Best-effort: one failed módulo in the outline (already marked
            # 'erro' by the pipelines) shouldn't stop the rest from being generated.
            logger.warning(
                "Falha ao gerar módulo '%s' (ordem=%s) na divisão automática: %s",
                planejado.titulo,
                ordem,
                exc.detail,
            )
            continue
        modulo_repo.refresh(modulo)

    return criados


def atualizar_modulo(
    tema_id: uuid.UUID,
    modulo_id: uuid.UUID,
    titulo: str | None,
    descricao: str | None,
    ordem: int | None,
    modulo_repo: ModuloRepository,
) -> Modulo:
    modulo = modulo_repo.get(modulo_id)
    if modulo is None or modulo.tema_id != tema_id:
        raise ModuloNaoEncontradoException(modulo_id)
    if titulo is not None:
        modulo.titulo = titulo
    if descricao is not None:
        modulo.descricao = descricao
    if ordem is not None:
        modulo.ordem = ordem
    modulo_repo.add(modulo)
    if ordem is not None:
        _commit_com_ordem(modulo_repo, ordem)
    else:
        modulo_repo.commit()
    modulo_repo.refresh(modulo)
    return modulo


def deletar_modulo(tema_id: uuid.UUID, modulo_id: uuid.UUID, modulo_repo: ModuloRepository) -> None:
    modulo = modulo_repo.get(modulo_id)
    if modulo is None or modulo.tema_id != tema_id:
        raise ModuloNaoEncontradoException(modulo_id)
    modulo_repo.delete(modulo)
    modulo_repo.commit()


def regenerar_modulo(
    tema_id: uuid.UUID,
    modulo_id: uuid.UUID,
    pool_size: int,
    tema_repo: TemaRepository,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
    *,
    instrucoes: str | None = None,
) -> Modulo:
    """`instrucoes` is optional admin feedback on what to change (e.g. "deixe
    mais curto", "adicione mais exemplos") - threaded into the content
    regeneration prompt. The quiz is always regenerated too, since it's
    written against this module's content and would drift out of sync
    otherwise."""
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)

    modulo = modulo_repo.get(modulo_id)
    if modulo is None or modulo.tema_id != tema_id:
        raise ModuloNaoEncontradoException(modulo_id)

    conteudo_ja_coberto = _conteudo_ja_coberto(tema, modulo.ordem, excluir_modulo_id=modulo.id)

    questionario_existente = questionario_repo.get_by_modulo(modulo_id)
    if questionario_existente is not None:
        modulo_repo.db.delete(questionario_existente)
    modulo.status = MODULO_STATUS_GERANDO
    modulo.conteudo = None
    modulo_repo.add(modulo)
    modulo_repo.commit()
    modulo_repo.refresh(modulo)

    gerar_conteudo_modulo(modulo, tema, modulo_repo, ai_provider, conteudo_ja_coberto, instrucoes)
    gerar_questionario_modulo(modulo, questionario_repo, modulo_repo, ai_provider, pool_size)
    modulo_repo.refresh(modulo)
    return modulo


def regenerar_questionario_modulo(
    tema_id: uuid.UUID,
    modulo_id: uuid.UUID,
    pool_size: int,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
) -> Modulo:
    """Rerolls just the quiz - one AI call, from the módulo's EXISTING
    content - without touching that content. Use `regenerar_modulo` instead
    when the content itself also needs to change."""
    modulo = modulo_repo.get(modulo_id)
    if modulo is None or modulo.tema_id != tema_id:
        raise ModuloNaoEncontradoException(modulo_id)
    if not modulo.conteudo:
        raise ConteudoIndisponivelException(
            "Este módulo ainda não tem conteúdo para gerar um questionário."
        )

    questionario_existente = questionario_repo.get_by_modulo(modulo_id)
    if questionario_existente is not None:
        modulo_repo.db.delete(questionario_existente)
    modulo.status = MODULO_STATUS_GERANDO
    modulo_repo.add(modulo)
    modulo_repo.commit()

    gerar_questionario_modulo(modulo, questionario_repo, modulo_repo, ai_provider, pool_size)
    modulo_repo.refresh(modulo)
    return modulo


def regenerar_questionarios_tema(
    tema_id: uuid.UUID,
    pool_size: int,
    tema_repo: TemaRepository,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
    ai_provider: AIProvider,
) -> list[Modulo]:
    """Bulk version of `regenerar_questionario_modulo` - rerolls the quiz for
    every módulo under this tema that already has content, one AI call each,
    content untouched. Módulos with no content yet are skipped, not failed;
    a failure regenerating one módulo's quiz doesn't stop the others."""
    tema = tema_repo.get_with_relations(tema_id)
    if tema is None:
        raise TemaNaoEncontradoException(tema_id)

    atualizados = []
    for modulo in sorted(tema.modulos, key=lambda m: m.ordem):
        if not modulo.conteudo:
            continue
        try:
            regenerar_questionario_modulo(
                tema_id, modulo.id, pool_size, modulo_repo, questionario_repo, ai_provider
            )
            atualizados.append(modulo)
        except AppException as exc:
            logger.warning(
                "Falha ao regenerar questionário do módulo '%s': %s", modulo.titulo, exc.detail
            )
            continue
    return atualizados


def editar_conteudo_modulo(
    modulo_id: uuid.UUID, conteudo: str, modulo_repo: ModuloRepository
) -> Modulo:
    """Manual edit of a módulo's already-generated content - no AI call."""
    modulo = modulo_repo.get(modulo_id)
    if modulo is None:
        raise ModuloNaoEncontradoException(modulo_id)
    modulo_repo.atualizar_conteudo(modulo, conteudo)
    modulo_repo.commit()
    modulo_repo.refresh(modulo)
    return modulo


# --- Questão ---


def editar_questao(
    modulo_id: uuid.UUID,
    questao_id: uuid.UUID,
    enunciado: str | None,
    alternativas: list[dict] | None,
    explicacao: str | None,
    resposta_correta: str | None,
    modulo_repo: ModuloRepository,
    questionario_repo: QuestionarioRepository,
) -> tuple[Questao, str]:
    """Manual correction of one already-generated questão - no AI call.
    Returns the updated questão plus its (possibly unchanged) correct answer."""
    if modulo_repo.get(modulo_id) is None:
        raise ModuloNaoEncontradoException(modulo_id)
    questionario = questionario_repo.get_by_modulo(modulo_id)
    if questionario is None:
        raise QuestionarioNaoEncontradoException(modulo_id)

    questao = questionario_repo.get_questao_by_id(questao_id)
    if questao is None or questao.questionario_id != questionario.id:
        raise QuestaoNaoEncontradaException(questao_id)

    questionario_repo.atualizar_questao(
        questao, enunciado=enunciado, alternativas=alternativas, explicacao=explicacao
    )
    if resposta_correta is not None:
        questionario_repo.atualizar_gabarito(questao_id, resposta_correta)
    questionario_repo.commit()
    questionario_repo.refresh(questao)

    resposta_atual = questionario_repo.get_gabarito_map([questao_id])[questao_id]
    return questao, resposta_atual
