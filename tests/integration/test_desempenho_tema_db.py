"""Runs `TentativaRepository.desempenho_por_tema` against real Postgres - the
join questão -> questionário -> módulo -> tema can't be exercised by the
in-memory fake. Requires TEST_DATABASE_URL (see tests/integration/conftest.py).
"""

from app.models.materia import Materia
from app.models.modulo import STATUS_PRONTO, Modulo
from app.models.questao import Questao
from app.models.questionario import Questionario
from app.models.tema import Tema
from app.models.tentativa import STATUS_CONCLUIDA, RespostaTentativa, Tentativa
from app.repositories.tentativa_repository import TentativaRepository

USER = "user-desempenho"


def _tema_com_questoes(db, materia, ordem, num_questoes):
    tema = Tema(materia_id=materia.id, titulo=f"Tema {ordem}", ordem=ordem, status=STATUS_PRONTO)
    db.add(tema)
    db.flush()
    modulo = Modulo(tema_id=tema.id, titulo="Módulo", ordem=0, status=STATUS_PRONTO)
    db.add(modulo)
    db.flush()
    questionario = Questionario(modulo_id=modulo.id, modelo_ia="fake")
    db.add(questionario)
    db.flush()
    questoes = [
        Questao(
            questionario_id=questionario.id,
            ordem=i,
            enunciado=f"Q{i}",
            alternativas=[{"letra": letra, "texto": letra} for letra in "ABCDE"],
        )
        for i in range(num_questoes)
    ]
    db.add_all(questoes)
    db.flush()
    return tema, questionario, questoes


def _tentativa(db, questionario, questoes, acertos, status=STATUS_CONCLUIDA, user_id=USER):
    tentativa = Tentativa(
        questionario_id=questionario.id,
        user_id=user_id,
        status=status,
        total_questoes=len(questoes),
    )
    db.add(tentativa)
    db.flush()
    db.add_all(
        RespostaTentativa(
            tentativa_id=tentativa.id,
            questao_id=q.id,
            resposta_escolhida="A",
            correta=i < acertos,
        )
        for i, q in enumerate(questoes)
    )
    db.flush()


def test_desempenho_por_tema_agrupa_por_tema_e_ignora_nao_concluidas_e_outros_alunos(db_session):
    materia = Materia(nome="Matemática (desempenho)")
    db_session.add(materia)
    db_session.flush()
    tema_a, quiz_a, questoes_a = _tema_com_questoes(db_session, materia, 0, 4)
    tema_b, quiz_b, questoes_b = _tema_com_questoes(db_session, materia, 1, 3)

    _tentativa(db_session, quiz_a, questoes_a, acertos=3)
    _tentativa(db_session, quiz_b, questoes_b, acertos=0)
    _tentativa(db_session, quiz_b, questoes_b, acertos=3, status="em_andamento")  # not counted
    _tentativa(db_session, quiz_a, questoes_a, acertos=4, user_id="outro-aluno")  # not counted

    desempenho = TentativaRepository(db_session).desempenho_por_tema(USER)

    assert desempenho == {tema_a.id: (3, 4), tema_b.id: (0, 3)}
