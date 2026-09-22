import uuid

from app.models.xp import MOTIVO_REPROVACAO_FINAL
from app.services import xp_service


def test_xp_necessario_para_nivel_cresce_20_por_cento():
    assert xp_service.xp_necessario_para_nivel(1) == 500
    assert xp_service.xp_necessario_para_nivel(2) == 600
    assert xp_service.xp_necessario_para_nivel(3) == 720
    assert xp_service.xp_necessario_para_nivel(4) == 864


def test_calcular_nivel_abaixo_do_minimo_e_nivel_zero():
    info = xp_service.calcular_nivel(0)
    assert info.nivel == 0
    assert info.xp_proximo_nivel == 500
    assert info.xp_faltando_proximo_nivel == 500


def test_calcular_nivel_exatamente_no_limiar_conta_para_o_nivel():
    info = xp_service.calcular_nivel(500)
    assert info.nivel == 1
    assert info.xp_proximo_nivel == 600
    assert info.xp_faltando_proximo_nivel == 100


def test_calcular_nivel_entre_limiares():
    info = xp_service.calcular_nivel(650)
    assert info.nivel == 2
    assert info.xp_proximo_nivel == 720
    assert info.xp_faltando_proximo_nivel == 70


def _registrar(repo, pontuacao, *, limite=75.0, penalidade=30, era_primeira=True, melhoria=0.0):
    xp_service.registrar_xp_por_tentativa(
        "user-1",
        uuid.uuid4(),
        uuid.uuid4(),
        pontuacao,
        limite,
        penalidade,
        era_primeira,
        melhoria,
        repo,
    )


def test_reprovar_nao_da_xp_e_aplica_penalidade_negativa():
    from tests.fakes.in_memory_repositories import InMemoryXpRepository

    repo = InMemoryXpRepository()
    _registrar(repo, 40.0)

    assert len(repo.eventos) == 1
    assert repo.eventos[0].quantidade == -30
    assert repo.eventos[0].motivo == MOTIVO_REPROVACAO_FINAL


def test_penalidade_zero_nao_registra_evento():
    from tests.fakes.in_memory_repositories import InMemoryXpRepository

    repo = InMemoryXpRepository()
    _registrar(repo, 40.0, penalidade=0)

    assert repo.eventos == []


def test_primeira_tentativa_aprovada_mantem_as_faixas():
    from tests.fakes.in_memory_repositories import InMemoryXpRepository

    for pontuacao, esperado in ((75.0, 80), (90.0, 100), (100.0, 200)):
        repo = InMemoryXpRepository()
        _registrar(repo, pontuacao)
        assert repo.eventos[0].quantidade == esperado


def test_retentativa_aprovada_com_melhoria_ganha_a_diferenca():
    from tests.fakes.in_memory_repositories import InMemoryXpRepository

    repo = InMemoryXpRepository()
    _registrar(repo, 80.0, era_primeira=False, melhoria=10.0)

    assert repo.eventos[0].quantidade == 10


def test_retentativa_aprovada_sem_melhoria_nao_ganha_nada():
    from tests.fakes.in_memory_repositories import InMemoryXpRepository

    repo = InMemoryXpRepository()
    _registrar(repo, 80.0, era_primeira=False, melhoria=0.0)

    assert repo.eventos == []
