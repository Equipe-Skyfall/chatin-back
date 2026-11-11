"""Ranking positions and apelido uniqueness against real Postgres. Requires
TEST_DATABASE_URL (see tests/integration/conftest.py)."""

import pytest

from app.core.exceptions import ApelidoEmUsoException
from app.models.materia import Materia
from app.models.perfil import PerfilUsuario
from app.models.xp import MOTIVO_PRIMEIRA_TENTATIVA, XpEvento
from app.repositories.perfil_repository import PerfilRepository
from app.repositories.xp_repository import XpRepository


def _xp(db, materia, user_id, quantidade):
    db.add(
        XpEvento(
            user_id=user_id,
            materia_id=materia.id,
            quantidade=quantidade,
            motivo=MOTIVO_PRIMEIRA_TENTATIVA,
        )
    )


def test_posicao_global_segue_a_ordem_do_ranking_inclusive_nos_empates(db_session):
    materia = Materia(nome="Ranking (posição)")
    db_session.add(materia)
    db_session.flush()
    for user_id, quantidade in [("rk-a", 100), ("rk-b", 100), ("rk-c", 50), ("rk-d", 70)]:
        _xp(db_session, materia, user_id, quantidade)
    db_session.flush()
    repo = XpRepository(db_session)

    assert repo.ranking_por_materia(materia.id, 10) == [
        ("rk-a", 100),
        ("rk-b", 100),
        ("rk-d", 70),
        ("rk-c", 50),
    ]
    assert [repo.posicao_por_materia(u, materia.id) for u in ("rk-a", "rk-b", "rk-d", "rk-c")] == [
        (1, 100),
        (2, 100),
        (3, 70),
        (4, 50),
    ]
    assert repo.posicao_por_materia("rk-sem-xp", materia.id) is None


def test_apelido_e_unico_sem_diferenciar_maiusculas_e_nao_vaza_para_outros(db_session):
    db_session.add_all([PerfilUsuario(user_id="ap-1"), PerfilUsuario(user_id="ap-2")])
    db_session.flush()
    repo = PerfilRepository(db_session)

    repo.definir_apelido("ap-1", "Ana Lu")
    repo.definir_apelido("ap-1", "Ana Luiza")

    with pytest.raises(ApelidoEmUsoException):
        repo.definir_apelido("ap-2", "ana luiza")
    assert repo.apelido_de("ap-2") is None
    assert repo.apelidos_por_ids(["ap-1", "ap-2"]) == {"ap-1": "Ana Luiza"}
