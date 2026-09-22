"""Unit tests for the student agent's tools (`agent_tools_aluno.py`) -
mirrors the admin's `test_agent_tools`-style approach (not present as a
separate file today; the admin tools are covered via `test_agent_service.py`
+ integration tests instead), exercised through `executar_ferramenta_aluno`
so dispatch + error-handling is covered too, not just the bare functions.
"""

import uuid

from app.ai.schemas import FerramentaContexto
from app.core.exceptions import MateriaNaoEncontradaException
from app.models.materia import Materia
from app.models.progresso import ProgressoUsuario
from app.models.tema import Tema
from app.services.agent_tools_aluno import executar_ferramenta_aluno


class _FakeMateriaRepository:
    def __init__(self):
        self.materias: dict[uuid.UUID, Materia] = {}
        self.rollbacks = 0

    def seed(self, materia: Materia) -> None:
        self.materias[materia.id] = materia

    def get(self, materia_id: uuid.UUID) -> Materia | None:
        return self.materias.get(materia_id)

    def list_publica(self) -> list[Materia]:
        return list(self.materias.values())

    def list_minhas_e_globais(self, user_id: str) -> list[Materia]:
        return [m for m in self.materias.values() if m.owner_user_id in (None, user_id)]

    def list_minhas_e_globais_with_temas_e_modulos(self, user_id: str) -> list[Materia]:
        return self.list_minhas_e_globais(user_id)

    def add(self, materia: Materia) -> Materia:
        if materia.id is None:
            materia.id = uuid.uuid4()
        self.materias[materia.id] = materia
        return materia

    def commit(self) -> None:
        pass

    def refresh(self, materia: Materia) -> None:
        pass

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeTemaRepository:
    def __init__(self):
        self.temas: dict[uuid.UUID, Tema] = {}

    def list_by_materia(self, materia_id: uuid.UUID) -> list[Tema]:
        return [t for t in self.temas.values() if t.materia_id == materia_id]

    def add(self, tema: Tema) -> Tema:
        if tema.id is None:
            tema.id = uuid.uuid4()
        self.temas[tema.id] = tema
        return tema

    def commit(self) -> None:
        pass

    def refresh(self, tema: Tema) -> None:
        pass


class _FakeVotoRepository:
    def __init__(self, scores: dict[uuid.UUID, int] | None = None):
        self._scores = scores or {}

    def scores_por_materias(self, materia_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        return {mid: self._scores[mid] for mid in materia_ids if mid in self._scores}


class _FakeXpRepository:
    def __init__(self, por_materia: dict[uuid.UUID, int] | None = None):
        self._por_materia = por_materia or {}

    def total_por_usuario_e_materia(self, user_id: str, materia_id: uuid.UUID) -> int:
        return self._por_materia.get(materia_id, 0)


class _FakeProgressoRepository:
    def __init__(self, rows: list[ProgressoUsuario] | None = None):
        self._rows = rows or []

    def list_by_user_and_modulos(
        self, user_id: str, modulo_ids: list[uuid.UUID]
    ) -> list[ProgressoUsuario]:
        return [r for r in self._rows if r.modulo_id in modulo_ids]


class _FakeBackgroundTasks:
    """Records scheduled calls without running them - matches how a real
    `BackgroundTasks` behaves (it only runs after the response is sent), and
    keeps this test from needing a real DB session."""

    def __init__(self):
        self.tarefas: list[tuple] = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.tarefas.append((func, args, kwargs))


def _ctx(
    *,
    user_id: str = "aluno-1",
    materia_repo: _FakeMateriaRepository | None = None,
    tema_repo: _FakeTemaRepository | None = None,
    voto_repo: _FakeVotoRepository | None = None,
    xp_repo: _FakeXpRepository | None = None,
    progresso_repo: _FakeProgressoRepository | None = None,
    background_tasks: _FakeBackgroundTasks | None = None,
) -> FerramentaContexto:
    return FerramentaContexto(
        materia_repo=materia_repo or _FakeMateriaRepository(),
        tema_repo=tema_repo or _FakeTemaRepository(),
        modulo_repo=None,
        questionario_repo=None,
        xp_repo=xp_repo or _FakeXpRepository(),
        progresso_repo=progresso_repo or _FakeProgressoRepository(),
        voto_repo=voto_repo or _FakeVotoRepository(),
        ai_provider=None,
        pool_size=12,
        user_id=user_id,
        conversa_id=uuid.uuid4(),
        background_tasks=background_tasks,
    )


# --- buscar_conteudo ---


def test_buscar_conteudo_nao_preenche_ids_de_criacao():
    """`materia_criada_id`/`tema_criado_id` on `ctx` are only ever written by
    `criar_minha_trilha` - a tool that doesn't create anything must leave
    them `None`, so the router doesn't hand back stale/wrong ids from an
    earlier turn on the same `ctx` (each request builds a fresh `ctx`, but
    the invariant is worth locking down directly)."""
    ctx = _ctx()
    executar_ferramenta_aluno("buscar_conteudo", {"termo": "x"}, ctx)
    assert ctx.materia_criada_id is None
    assert ctx.tema_criado_id is None


def test_buscar_conteudo_sem_termo_pede_termo():
    resultado = executar_ferramenta_aluno("buscar_conteudo", {"termo": ""}, _ctx())
    assert "Informe um termo" in resultado


def test_buscar_conteudo_encontra_por_nome():
    materia_repo = _FakeMateriaRepository()
    materia_repo.seed(Materia(id=uuid.uuid4(), nome="Cálculo 1", owner_user_id=None))
    ctx = _ctx(materia_repo=materia_repo)

    resultado = executar_ferramenta_aluno("buscar_conteudo", {"termo": "cálculo"}, ctx)

    assert "Cálculo 1" in resultado
    assert "currículo oficial" in resultado


def test_buscar_conteudo_sem_resultado_sugere_criar():
    resultado = executar_ferramenta_aluno("buscar_conteudo", {"termo": "topologia"}, _ctx())
    assert "criar_minha_trilha" in resultado


def test_buscar_conteudo_mostra_origem_e_votos_de_trilha_de_outro_aluno():
    materia_repo = _FakeMateriaRepository()
    outra = Materia(id=uuid.uuid4(), nome="Química Divertida", owner_user_id="aluno-2")
    materia_repo.seed(outra)
    voto_repo = _FakeVotoRepository({outra.id: 3})
    ctx = _ctx(materia_repo=materia_repo, voto_repo=voto_repo, user_id="aluno-1")

    resultado = executar_ferramenta_aluno("buscar_conteudo", {"termo": "química"}, ctx)

    assert "trilha de outro aluno" in resultado
    assert "votos=3" in resultado


# --- meu_desempenho ---


def test_meu_desempenho_sem_progresso():
    resultado = executar_ferramenta_aluno("meu_desempenho", {}, _ctx())
    assert "nenhum progresso" in resultado.lower()


def test_meu_desempenho_filtra_por_nome_inexistente():
    materia_repo = _FakeMateriaRepository()
    materia_repo.seed(Materia(id=uuid.uuid4(), nome="Física", owner_user_id=None))
    ctx = _ctx(materia_repo=materia_repo)

    resultado = executar_ferramenta_aluno(
        "meu_desempenho", {"materia_nome": "Biologia"}, ctx
    )

    assert "Nenhuma matéria encontrada" in resultado


# --- criar_minha_trilha ---


def test_criar_minha_trilha_sem_argumentos_pede_ambos():
    resultado = executar_ferramenta_aluno("criar_minha_trilha", {}, _ctx())
    assert "nome_materia" in resultado and "titulo_tema" in resultado


def test_criar_minha_trilha_cria_materia_e_tema_e_agenda_background_task():
    materia_repo = _FakeMateriaRepository()
    tema_repo = _FakeTemaRepository()
    background_tasks = _FakeBackgroundTasks()
    ctx = _ctx(
        materia_repo=materia_repo,
        tema_repo=tema_repo,
        background_tasks=background_tasks,
        user_id="aluno-1",
    )

    resultado = executar_ferramenta_aluno(
        "criar_minha_trilha",
        {"nome_materia": "Química Orgânica", "titulo_tema": "Hidrocarbonetos"},
        ctx,
    )

    (materia,) = materia_repo.materias.values()
    assert materia.owner_user_id == "aluno-1"
    assert materia.nome == "Química Orgânica"
    (tema,) = tema_repo.temas.values()
    assert tema.titulo == "Hidrocarbonetos"
    assert tema.materia_id == materia.id
    assert str(materia.id) in resultado and str(tema.id) in resultado
    assert "gerando" in resultado.lower() or "leva um" in resultado.lower()

    # ctx is written to (not just the text reply) so the router can hand
    # structured ids back to the frontend without parsing the model's text
    assert ctx.materia_criada_id == materia.id
    assert ctx.tema_criado_id == tema.id

    # scheduled, not run inline - no AI/DB work happened synchronously
    assert len(background_tasks.tarefas) == 1
    func, args, _ = background_tasks.tarefas[0]
    assert func.__name__ == "completar_criacao_tema"
    assert args[0] == tema.id


def test_criar_minha_trilha_reusa_materia_existente_do_mesmo_aluno():
    materia_repo = _FakeMateriaRepository()
    existente = Materia(id=uuid.uuid4(), nome="Química Orgânica", owner_user_id="aluno-1")
    materia_repo.seed(existente)
    tema_repo = _FakeTemaRepository()
    ctx = _ctx(
        materia_repo=materia_repo,
        tema_repo=tema_repo,
        background_tasks=_FakeBackgroundTasks(),
        user_id="aluno-1",
    )

    executar_ferramenta_aluno(
        "criar_minha_trilha",
        {"nome_materia": "química orgânica", "titulo_tema": "Alcanos"},
        ctx,
    )

    assert len(materia_repo.materias) == 1  # no duplicate matéria created
    (tema,) = tema_repo.temas.values()
    assert tema.materia_id == existente.id


def test_ferramenta_inexistente_retorna_erro_sem_lancar():
    resultado = executar_ferramenta_aluno("apagar_tudo", {}, _ctx())
    assert resultado.startswith("Erro:")


def test_erro_de_dominio_vira_string_erro_nao_excecao():
    materia_repo = _FakeMateriaRepository()  # materia inexistente

    def _get_boom(_id):
        raise MateriaNaoEncontradaException(uuid.uuid4())

    materia_repo.get = _get_boom
    tema_repo = _FakeTemaRepository()
    ctx = _ctx(
        materia_repo=materia_repo, tema_repo=tema_repo, background_tasks=_FakeBackgroundTasks()
    )

    resultado = executar_ferramenta_aluno(
        "criar_minha_trilha", {"nome_materia": "X", "titulo_tema": "Y"}, ctx
    )

    assert resultado.startswith("Erro:")
