"""Explorar trilhas / trilhas estudadas against a real Postgres: the grouped
stats queries, the visibility rules and the monthly count."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO, Modulo
from app.models.perfil import PerfilUsuario
from app.models.progresso import ProgressoUsuario
from app.models.tema import Tema
from app.models.trilha_estudando import TrilhaEstudando
from app.models.voto_materia import VotoMateria
from app.repositories.materia_repository import MateriaRepository
from app.repositories.trilha_estudando_repository import TrilhaEstudandoRepository
from app.repositories.trilha_explorar_repository import TrilhaExplorarRepository

SUFIXO = uuid.uuid4().hex[:6]


def _trilha(db, nome, owner=None, modulos_prontos=1, criada=None):
    materia = Materia(nome=f"{nome}-{SUFIXO}", owner_user_id=owner)
    if criada:
        materia.created_at = criada
    db.add(materia)
    db.flush()
    tema = Tema(materia_id=materia.id, titulo="Tema", ordem=0, status=STATUS_PRONTO)
    db.add(tema)
    db.flush()
    modulos = []
    for i in range(modulos_prontos):
        modulo = Modulo(tema_id=tema.id, titulo=f"M{i}", ordem=i, status=STATUS_PRONTO)
        db.add(modulo)
        modulos.append(modulo)
    db.flush()
    return materia, modulos


def _nomes(itens):
    return [i.materia.nome.rsplit("-", 1)[0] for i in itens if i.materia.nome.endswith(SUFIXO)]


def test_origem_e_visibilidade(db_session):
    db = db_session
    _trilha(db, "Oficial")
    _trilha(db, "DeOutro", owner="u-outro")
    _trilha(db, "Vazia", owner="u-outro", modulos_prontos=0)
    _trilha(db, "MinhaVazia", owner="u-eu", modulos_prontos=0)
    repo = TrilhaExplorarRepository(db)

    todas = _nomes(repo.listar("u-eu", "todas", "recentes", 50, 0))
    assert set(todas) == {"Oficial", "DeOutro", "MinhaVazia"}  # a vazia de outro não aparece
    assert _nomes(repo.listar("u-eu", "verificadas", "recentes", 50, 0)) == ["Oficial"]
    assert set(_nomes(repo.listar("u-eu", "comunidade", "recentes", 50, 0))) == {
        "DeOutro",
        "MinhaVazia",
    }


def test_stats_votos_alunos_autor_e_estudando(db_session):
    db = db_session
    db.add(PerfilUsuario(user_id="u-autor", nome="Ana Autora"))
    materia, modulos = _trilha(db, "Popular", owner="u-autor", modulos_prontos=3)
    db.add_all(
        [
            VotoMateria(user_id="a", materia_id=materia.id, valor=1),
            VotoMateria(user_id="b", materia_id=materia.id, valor=1),
            VotoMateria(user_id="u-eu", materia_id=materia.id, valor=-1),
            TrilhaEstudando(user_id="a", materia_id=materia.id),
            ProgressoUsuario(user_id="b", modulo_id=modulos[0].id),
        ]
    )
    db.flush()

    (item,) = [
        i
        for i in TrilhaExplorarRepository(db).listar("u-eu", "comunidade", "votos", 50, 0)
        if i.materia.id == materia.id
    ]

    assert (item.votos, item.meu_voto) == (1, -1)
    assert (item.temas, item.modulos) == (1, 3)
    assert item.alunos == 3  # a (adotou) + b (progresso) + u-autor (autor)
    assert item.autor_nome == "Ana Autora"
    assert item.estudando is False and item.pronta is True


def test_ordem_por_votos_e_por_alunos(db_session):
    db = db_session
    a, _ = _trilha(db, "ComVoto", owner="x")
    b, _ = _trilha(db, "ComAlunos", owner="y")
    db.add_all(
        [
            VotoMateria(user_id="v1", materia_id=a.id, valor=1),
            TrilhaEstudando(user_id="e1", materia_id=b.id),
            TrilhaEstudando(user_id="e2", materia_id=b.id),
            TrilhaEstudando(user_id="e3", materia_id=b.id),
        ]
    )
    db.flush()
    repo = TrilhaExplorarRepository(db)

    por_votos = _nomes(repo.listar("u-eu", "comunidade", "votos", 50, 0))
    por_alunos = _nomes(repo.listar("u-eu", "comunidade", "alunos", 50, 0))

    assert por_votos.index("ComVoto") < por_votos.index("ComAlunos")
    assert por_alunos.index("ComAlunos") < por_alunos.index("ComVoto")


def test_paginacao(db_session):
    db = db_session
    for i in range(3):
        _trilha(db, f"Pag{i}", owner="p")
    repo = TrilhaExplorarRepository(db)

    primeira = repo.listar("u-eu", "comunidade", "recentes", 2, 0)
    segunda = repo.listar("u-eu", "comunidade", "recentes", 2, 2)

    assert len(primeira) == 2
    assert {i.materia.id for i in primeira}.isdisjoint({i.materia.id for i in segunda})


def test_listar_custa_um_numero_fixo_de_consultas(db_session):
    db = db_session
    for i in range(6):
        _trilha(db, f"N1-{i}", owner=f"dono{i}")
    consultas = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda *a: consultas.append(a[2]))
    TrilhaExplorarRepository(db).listar("u-eu", "todas", "votos", 50, 0)
    # Um SELECT só, com as estatísticas em sub-consultas agrupadas (sem N+1).
    assert len(consultas) == 1


def test_estudadas_incluem_globais_proprias_e_adotadas_mas_nao_as_de_outros(db_session):
    db = db_session
    oficial, _ = _trilha(db, "Oficial2")
    propria, _ = _trilha(db, "Propria2", owner="u-eu")
    adotada, _ = _trilha(db, "Adotada2", owner="u-outro")
    ignorada, _ = _trilha(db, "Ignorada2", owner="u-outro")
    db.add(TrilhaEstudando(user_id="u-eu", materia_id=adotada.id))
    db.flush()

    ids = {m.id for m in MateriaRepository(db).list_minhas_e_globais_with_temas_e_modulos("u-eu")}

    assert {oficial.id, propria.id, adotada.id} <= ids
    assert ignorada.id not in ids


def test_adocao_e_idempotente_e_removivel(db_session):
    db = db_session
    materia, _ = _trilha(db, "Adocao", owner="u-outro")
    repo = TrilhaEstudandoRepository(db)

    repo.adicionar("u-eu", materia.id)
    repo.adicionar("u-eu", materia.id)
    assert repo.ids_do_usuario("u-eu") >= {materia.id}
    assert repo.existe("u-eu", materia.id)

    repo.remover("u-eu", materia.id)
    assert not repo.existe("u-eu", materia.id)


def test_contagem_mensal_so_conta_as_do_aluno_desde_o_inicio_do_mes(db_session):
    db = db_session
    agora = datetime.now(UTC)
    _trilha(db, "Nova", owner="u-cota", criada=agora)
    _trilha(db, "Velha", owner="u-cota", criada=agora - timedelta(days=90))
    _trilha(db, "DeOutro", owner="u-outro-cota", criada=agora)
    repo = MateriaRepository(db)

    assert repo.count_criadas_desde("u-cota", agora - timedelta(days=1)) == 1
    assert repo.count_criadas_desde("u-cota", agora - timedelta(days=365)) == 2
