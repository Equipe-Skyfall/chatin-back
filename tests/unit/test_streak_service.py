from datetime import date, timedelta

from app.models.streak import StreakUsuario
from app.models.xp import MOTIVO_STREAK_DIARIO
from app.services import streak_service
from tests.fakes.in_memory_repositories import InMemoryStreakRepository, InMemoryXpRepository

DIA = date(2026, 11, 2)  # a Monday


def _acessar(streak_repo, xp_repo, dia, user="aluno-1"):
    streak_service.registrar_acesso_diario(user, streak_repo, xp_repo, dia)


def test_primeiro_dia_inicia_a_sequencia_sem_xp():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()

    _acessar(streak_repo, xp_repo, DIA)

    assert streak_repo.get_by_user("aluno-1").sequencia == 1
    assert xp_repo.eventos == []


def test_dia_seguinte_estende_a_sequencia_e_da_xp():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()

    _acessar(streak_repo, xp_repo, DIA)
    _acessar(streak_repo, xp_repo, DIA + timedelta(days=1))

    assert streak_repo.get_by_user("aluno-1").sequencia == 2
    (evento,) = xp_repo.eventos
    assert evento.quantidade == streak_service.XP_STREAK_DIA
    assert evento.motivo == MOTIVO_STREAK_DIARIO
    assert evento.materia_id is None


def test_varios_acessos_no_mesmo_dia_contam_uma_vez_so():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()

    _acessar(streak_repo, xp_repo, DIA)
    for _ in range(3):
        _acessar(streak_repo, xp_repo, DIA + timedelta(days=1))

    assert streak_repo.get_by_user("aluno-1").sequencia == 2
    assert len(xp_repo.eventos) == 1


def test_pular_um_dia_perde_a_sequencia_e_recomeca_em_1_sem_xp():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()
    for i in range(3):
        _acessar(streak_repo, xp_repo, DIA + timedelta(days=i))
    xp_antes = xp_repo.total_por_usuario("aluno-1")

    _acessar(streak_repo, xp_repo, DIA + timedelta(days=5))  # skipped two days

    assert streak_repo.get_by_user("aluno-1").sequencia == 1
    assert xp_repo.total_por_usuario("aluno-1") == xp_antes


def test_setimo_dia_seguido_ganha_o_bonus_da_semana():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()

    for i in range(7):
        _acessar(streak_repo, xp_repo, DIA + timedelta(days=i))

    quantidades = [e.quantidade for e in xp_repo.eventos]
    assert quantidades == [10] * 5 + [10 + streak_service.XP_STREAK_SEMANA]


def test_xp_do_dia():
    assert streak_service.xp_do_dia(1) == 0
    assert streak_service.xp_do_dia(2) == 10
    assert streak_service.xp_do_dia(7) == 60
    assert streak_service.xp_do_dia(14) == 60
    assert streak_service.xp_do_dia(8) == 10


def test_sequencia_atual_vale_hoje_ou_ontem_e_zera_depois():
    registro = StreakUsuario(user_id="a", sequencia=4, ultimo_dia=DIA)

    assert streak_service.sequencia_atual(registro, DIA) == 4
    assert streak_service.sequencia_atual(registro, DIA + timedelta(days=1)) == 4
    assert streak_service.sequencia_atual(registro, DIA + timedelta(days=2)) == 0
    assert streak_service.sequencia_atual(None, DIA) == 0


def test_streak_de_um_aluno_nao_afeta_o_de_outro():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()

    _acessar(streak_repo, xp_repo, DIA, "a")
    _acessar(streak_repo, xp_repo, DIA + timedelta(days=1), "a")
    _acessar(streak_repo, xp_repo, DIA + timedelta(days=1), "b")

    assert streak_repo.get_by_user("a").sequencia == 2
    assert streak_repo.get_by_user("b").sequencia == 1
    assert xp_repo.total_por_usuario("b") == 0


def test_falha_no_banco_nao_derruba_a_requisicao():
    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()
    streak_repo.falhar = True

    _acessar(streak_repo, xp_repo, DIA)  # must not raise

    assert streak_repo.rollbacks == 1
    assert xp_repo.eventos == []


def test_requisicao_autenticada_conta_o_dia_e_nao_falha_se_o_streak_falhar():
    from app.core.security import TokenPayload
    from app.deps import get_current_user_id

    class _Perfil:
        def upsert(self, *args):
            pass

    streak_repo, xp_repo = InMemoryStreakRepository(), InMemoryXpRepository()
    payload = TokenPayload(user_id="aluno-9", role="aluno")

    assert get_current_user_id(payload, _Perfil(), streak_repo, xp_repo) == "aluno-9"
    assert streak_repo.get_by_user("aluno-9").sequencia == 1

    streak_repo.falhar = True
    assert get_current_user_id(payload, _Perfil(), streak_repo, xp_repo) == "aluno-9"
