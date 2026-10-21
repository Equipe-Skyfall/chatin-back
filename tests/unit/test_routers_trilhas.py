"""Trilhas verificadas/da comunidade, cota mensal e adoção, sobre HTTP."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import MateriaNaoEncontradaException, NaoPodePararDeEstudarException
from app.models.materia import Materia
from app.repositories.trilha_explorar_repository import ItemExplorar
from app.services import trilha_estudo_service

USER = "aluno-1"


class _MateriaRepo:
    def __init__(self, materias=(), criadas=0):
        self.materias = {m.id: m for m in materias}
        self.criadas = criadas
        self.adicionadas: list[Materia] = []

    def get(self, materia_id):
        return self.materias.get(materia_id)

    def count_criadas_desde(self, user_id, desde):
        return self.criadas

    def add(self, materia):
        materia.id = materia.id or uuid.uuid4()
        materia.created_at = datetime.now(UTC)
        self.adicionadas.append(materia)

    def commit(self):
        pass

    def refresh(self, materia):
        pass

    def list_by_materia_with_modulos(self, materia_id):
        return []


def _materia(owner=None):
    return Materia(id=uuid.uuid4(), nome="X", owner_user_id=owner, created_at=datetime.now(UTC))


# --- adoção (service) ---


def test_estudar_trilha_da_comunidade_grava_e_e_idempotente(trilha_estudando_repo):
    alheia = _materia("outro")
    repo = _MateriaRepo([alheia])

    trilha_estudo_service.estudar(USER, alheia.id, repo, trilha_estudando_repo)
    trilha_estudo_service.estudar(USER, alheia.id, repo, trilha_estudando_repo)

    assert trilha_estudando_repo.ids_do_usuario(USER) == {alheia.id}


@pytest.mark.parametrize("dono", [None, USER])
def test_estudar_curriculo_verificado_ou_propria_nao_grava_nada(trilha_estudando_repo, dono):
    materia = _materia(dono)

    trilha_estudo_service.estudar(USER, materia.id, _MateriaRepo([materia]), trilha_estudando_repo)

    assert trilha_estudando_repo.adocoes == set()


def test_estudar_trilha_inexistente_levanta_404(trilha_estudando_repo):
    with pytest.raises(MateriaNaoEncontradaException):
        trilha_estudo_service.estudar(USER, uuid.uuid4(), _MateriaRepo(), trilha_estudando_repo)


def test_parar_de_estudar_remove_a_adocao(trilha_estudando_repo):
    alheia = _materia("outro")
    trilha_estudando_repo.adicionar(USER, alheia.id)

    trilha_estudo_service.parar_de_estudar(
        USER, alheia.id, _MateriaRepo([alheia]), trilha_estudando_repo
    )

    assert trilha_estudando_repo.adocoes == set()


@pytest.mark.parametrize("dono", [None, USER])
def test_nao_sai_de_curriculo_verificado_nem_da_propria_trilha(trilha_estudando_repo, dono):
    materia = _materia(dono)

    with pytest.raises(NaoPodePararDeEstudarException):
        trilha_estudo_service.parar_de_estudar(
            USER, materia.id, _MateriaRepo([materia]), trilha_estudando_repo
        )


# --- HTTP ---


@pytest.fixture
def api(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("TRILHAS_POR_MES", "3")
    get_settings.cache_clear()

    from app.core.security import TokenPayload
    from app.deps import get_current_user_id, get_token_payload
    from app.main import app
    from app.repositories.materia_repository import get_materia_repository
    from app.repositories.trilha_explorar_repository import get_trilha_explorar_repository

    estado = SimpleNamespace(
        role="USER", materias=_MateriaRepo(), explorar=None, overrides={}, app=app
    )

    def aplicar():
        app.dependency_overrides[get_current_user_id] = lambda: USER
        app.dependency_overrides[get_token_payload] = lambda: TokenPayload(
            user_id=USER, role=estado.role
        )
        app.dependency_overrides[get_materia_repository] = lambda: estado.materias
        app.dependency_overrides[get_trilha_explorar_repository] = lambda: estado.explorar

    aplicar()
    try:
        yield SimpleNamespace(client=TestClient(app), estado=estado)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_cota_do_aluno(api):
    api.estado.materias = _MateriaRepo(criadas=2)

    corpo = api.client.get("/trilhas/cota").json()

    assert (corpo["limite"], corpo["usadas"], corpo["restantes"]) == (3, 2, 1)
    assert corpo["reseta_em"]


def test_cota_do_admin_nao_tem_limite(api):
    api.estado.role = "ADMIN"
    api.estado.materias = _MateriaRepo(criadas=50)

    corpo = api.client.get("/trilhas/cota").json()

    assert corpo["limite"] is None and corpo["restantes"] is None


def test_criar_trilha_ate_o_limite_e_bloqueio_na_quarta(api):
    api.estado.materias = _MateriaRepo(criadas=2)
    ok = api.client.post("/materias", json={"nome": "Terceira trilha"})
    assert ok.status_code == 201

    api.estado.materias = _MateriaRepo(criadas=3)
    bloqueada = api.client.post("/materias", json={"nome": "Quarta trilha"})

    assert bloqueada.status_code == 403
    corpo = bloqueada.json()
    assert corpo["code"] == "LIMITE_TRILHAS_MENSAL"
    assert corpo["limite"] == 3 and corpo["reseta_em"]
    assert api.estado.materias.adicionadas == []


def test_admin_cria_trilha_verificada_sem_limite(api):
    api.estado.role = "ADMIN"
    api.estado.materias = _MateriaRepo(criadas=99)

    resposta = api.client.post("/materias", json={"nome": "Oficial nova"})

    assert resposta.status_code == 201
    assert api.estado.materias.adicionadas[0].owner_user_id is None


class _Explorar:
    def __init__(self, itens):
        self.itens = itens
        self.chamadas = []

    def listar(self, user_id, origem, ordem, limite, offset):
        self.chamadas.append((user_id, origem, ordem, limite, offset))
        return self.itens

    def obter(self, user_id, materia_id):
        return next((i for i in self.itens if i.materia.id == materia_id), None)


def _item(owner=None, **extra):
    base = dict(
        materia=_materia(owner),
        autor_nome="Ana" if owner else None,
        temas=2,
        modulos=5,
        alunos=7,
        votos=4,
        meu_voto=1,
        estudando=owner is None,
        propria=owner == USER,
        pronta=True,
    )
    return ItemExplorar(**{**base, **extra})


def test_explorar_repassa_filtros_e_marca_verificada(api):
    api.estado.explorar = _Explorar([_item(None), _item("outro")])

    resposta = api.client.get("/trilhas/explorar?origem=comunidade&ordem=alunos&limite=5&offset=10")

    assert resposta.status_code == 200
    assert api.estado.explorar.chamadas == [(USER, "comunidade", "alunos", 5, 10)]
    verificada, comunidade = resposta.json()
    assert verificada["verificada"] is True and verificada["autor_nome"] is None
    assert comunidade["verificada"] is False and comunidade["autor_nome"] == "Ana"
    assert (comunidade["temas"], comunidade["modulos"], comunidade["alunos"]) == (2, 5, 7)


@pytest.mark.parametrize("query", ["origem=qualquer", "ordem=aleatoria", "limite=0", "limite=51"])
def test_explorar_valida_parametros(api, query):
    api.estado.explorar = _Explorar([])

    assert api.client.get(f"/trilhas/explorar?{query}").status_code == 422


def test_detalhe_de_trilha_inexistente_e_404(api):
    api.estado.explorar = _Explorar([])

    assert api.client.get(f"/trilhas/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize(
    ("gerar_modulos", "esperado"),
    [(True, "completar_criacao_trilha_pessoal"), (False, "completar_criacao_tema")],
)
def test_criar_tema_encadeia_a_geracao_de_modulos_so_quando_pedido(
    api, monkeypatch, gerar_modulos, esperado
):
    from app.models.tema import Tema
    from app.services import curriculo_service, trilha_pessoal_service

    propria = _materia(USER)
    api.estado.materias = _MateriaRepo([propria])
    tema = Tema(
        id=uuid.uuid4(),
        materia_id=propria.id,
        titulo="Tema",
        ordem=0,
        status="gerando",
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(curriculo_service, "criar_tema_pendente", lambda *a, **k: tema)
    chamadas = []
    monkeypatch.setattr(
        trilha_pessoal_service, "completar_criacao_tema", lambda *a: chamadas.append("tema")
    )
    monkeypatch.setattr(
        trilha_pessoal_service,
        "completar_criacao_trilha_pessoal",
        lambda *a: chamadas.append("trilha_pessoal"),
    )

    resposta = api.client.post(
        f"/materias/{propria.id}/temas",
        json={"titulo": "Hidrocarbonetos", "gerar_modulos": gerar_modulos},
    )

    assert resposta.status_code == 201
    assert chamadas == [
        {"completar_criacao_trilha_pessoal": "trilha_pessoal"}.get(esperado, "tema")
    ]
