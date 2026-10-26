import pytest

from app.ai import resiliencia
from app.ai.disponibilidade import (
    FALHAS_SEGUIDAS,
    JANELA_SEGUNDOS,
    DisponibilidadeIA,
    status_ia,
)
from app.core.exceptions import ProvedorIAIndisponivelException


class _Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def relogio() -> _Relogio:
    return _Relogio()


@pytest.fixture
def disponibilidade(relogio) -> DisponibilidadeIA:
    return DisponibilidadeIA(relogio)


def test_comeca_disponivel(disponibilidade):
    assert disponibilidade.disponivel() is True
    assert disponibilidade.segundos_ate_nova_tentativa() == 0


def test_uma_falha_isolada_nao_derruba_a_disponibilidade(disponibilidade):
    for _ in range(FALHAS_SEGUIDAS - 1):
        disponibilidade.registrar_falha()

    assert disponibilidade.disponivel() is True


def test_falhas_seguidas_marcam_como_indisponivel(disponibilidade):
    for _ in range(FALHAS_SEGUIDAS):
        disponibilidade.registrar_falha()

    assert disponibilidade.disponivel() is False
    assert disponibilidade.segundos_ate_nova_tentativa() == int(JANELA_SEGUNDOS)


def test_contagem_regressiva_acompanha_o_relogio(disponibilidade, relogio):
    for _ in range(FALHAS_SEGUIDAS):
        disponibilidade.registrar_falha()

    relogio.agora += 45.5

    assert disponibilidade.segundos_ate_nova_tentativa() == 15


def test_volta_a_ficar_disponivel_depois_da_janela(disponibilidade, relogio):
    for _ in range(FALHAS_SEGUIDAS):
        disponibilidade.registrar_falha()

    relogio.agora += JANELA_SEGUNDOS

    assert disponibilidade.disponivel() is True


def test_um_sucesso_zera_a_contagem(disponibilidade):
    for _ in range(FALHAS_SEGUIDAS):
        disponibilidade.registrar_falha()

    disponibilidade.registrar_sucesso()

    assert disponibilidade.disponivel() is True
    disponibilidade.registrar_falha()
    assert disponibilidade.disponivel() is True  # the count restarted from zero


def test_chamada_que_falha_depois_dos_retries_conta_como_uma_falha():
    @resiliencia.retry_transiente(tentativas=2, espera_max=1)
    def chamar():
        raise ProvedorIAIndisponivelException("fora do ar")

    for _ in range(FALHAS_SEGUIDAS):
        with pytest.raises(ProvedorIAIndisponivelException):
            chamar()

    assert status_ia.disponivel() is False


def test_chamada_bem_sucedida_limpa_o_estado_global():
    for _ in range(FALHAS_SEGUIDAS):
        status_ia.registrar_falha()

    @resiliencia.retry_transiente(tentativas=2, espera_max=1)
    def chamar():
        return "ok"

    assert chamar() == "ok"
    assert status_ia.disponivel() is True
