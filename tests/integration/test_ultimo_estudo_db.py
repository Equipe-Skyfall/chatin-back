"""Runs `TentativaRepository.ultimo_estudo_por_modulo` against real Postgres.
Requires TEST_DATABASE_URL (see tests/integration/conftest.py).
"""

from datetime import UTC, datetime

from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO, Modulo
from app.models.questionario import Questionario
from app.models.tema import Tema
from app.models.tentativa import STATUS_CONCLUIDA, STATUS_EM_ANDAMENTO, Tentativa
from app.repositories.tentativa_repository import TentativaRepository

USER = "user-ultimo-estudo"


def _modulo_com_questionario(db, materia, ordem):
    tema = Tema(materia_id=materia.id, titulo=f"Tema {ordem}", ordem=ordem, status=STATUS_PRONTO)
    db.add(tema)
    db.flush()
    modulo = Modulo(tema_id=tema.id, titulo="Módulo", ordem=0, status=STATUS_PRONTO)
    db.add(modulo)
    db.flush()
    questionario = Questionario(modulo_id=modulo.id, modelo_ia="fake")
    db.add(questionario)
    db.flush()
    return modulo, questionario, tema


def _tentativa(db, questionario, quando, status=STATUS_CONCLUIDA, user_id=USER, tema=None):
    db.add(
        Tentativa(
            questionario_id=None if tema else questionario.id,
            tema_id=tema.id if tema else None,
            user_id=user_id,
            status=status,
            total_questoes=1,
            created_at=quando,
        )
    )
    db.flush()


def test_ultimo_estudo_e_o_fim_mais_recente_por_modulo(db_session):
    materia = Materia(nome="Matemática (último estudo)")
    db_session.add(materia)
    db_session.flush()
    modulo_a, quiz_a, tema_a = _modulo_com_questionario(db_session, materia, 0)
    modulo_b, quiz_b, _ = _modulo_com_questionario(db_session, materia, 1)
    modulo_c, quiz_c, _ = _modulo_com_questionario(db_session, materia, 2)

    antigo = datetime(2026, 10, 1, tzinfo=UTC)
    recente = datetime(2026, 10, 10, tzinfo=UTC)
    _tentativa(db_session, quiz_a, antigo)
    _tentativa(db_session, quiz_a, recente)
    _tentativa(db_session, quiz_b, recente, status=STATUS_EM_ANDAMENTO)  # not counted
    _tentativa(db_session, quiz_b, antigo, user_id="outro-aluno")  # not counted
    _tentativa(db_session, None, recente, tema=tema_a)  # tema review: no single módulo

    ultimo = TentativaRepository(db_session).ultimo_estudo_por_modulo(USER)

    assert ultimo == {modulo_a.id: recente}
    assert modulo_b.id not in ultimo and modulo_c.id not in ultimo
