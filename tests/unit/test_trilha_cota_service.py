from datetime import UTC, datetime

import pytest

from app.core.exceptions import LimiteTrilhasMensalExcedidoException
from app.services import trilha_cota_service
from app.services.trilha_cota_service import FUSO_BR


class _Repo:
    def __init__(self, usadas: int):
        self.usadas = usadas
        self.desde: datetime | None = None

    def count_criadas_desde(self, user_id, desde):
        self.desde = desde
        return self.usadas


AGORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def test_mes_comeca_no_dia_1_meia_noite_do_horario_de_brasilia():
    assert trilha_cota_service.inicio_do_mes(AGORA) == datetime(2026, 10, 1, 0, 0, tzinfo=FUSO_BR)


def test_virada_do_mes_usa_o_fuso_brasileiro_e_nao_o_utc():
    # 02:00 UTC de 1º/nov ainda é 31/out à noite em Brasília.
    quase_novembro = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
    assert trilha_cota_service.inicio_do_mes(quase_novembro).month == 10


def test_reset_e_o_primeiro_dia_do_mes_seguinte_inclusive_na_virada_do_ano():
    assert trilha_cota_service.proximo_reset(AGORA).month == 11
    dezembro = datetime(2026, 12, 15, tzinfo=UTC)
    reset = trilha_cota_service.proximo_reset(dezembro)
    assert (reset.year, reset.month, reset.day) == (2027, 1, 1)


def test_calcula_usadas_e_restantes():
    cota = trilha_cota_service.calcular("u1", _Repo(2), 3, agora=AGORA)
    assert (cota.limite, cota.usadas, cota.restantes) == (3, 2, 1)


def test_cota_nao_fica_negativa():
    assert trilha_cota_service.calcular("u1", _Repo(7), 3, agora=AGORA).restantes == 0


def test_admin_nao_tem_limite_e_nem_consulta_o_banco():
    repo = _Repo(99)
    cota = trilha_cota_service.calcular("admin", repo, 3, admin=True, agora=AGORA)
    assert cota.limite is None and cota.restantes is None
    assert repo.desde is None
    trilha_cota_service.exigir_vaga("admin", repo, 3, admin=True, agora=AGORA)


def test_exigir_vaga_libera_enquanto_ha_restantes():
    trilha_cota_service.exigir_vaga("u1", _Repo(2), 3, agora=AGORA)


def test_exigir_vaga_bloqueia_ao_atingir_o_limite_com_code_e_dados():
    with pytest.raises(LimiteTrilhasMensalExcedidoException) as erro:
        trilha_cota_service.exigir_vaga("u1", _Repo(3), 3, agora=AGORA)

    assert erro.value.status_code == 403
    assert erro.value.code == "LIMITE_TRILHAS_MENSAL"
    assert erro.value.extra["limite"] == 3
    assert erro.value.extra["reseta_em"].startswith("2026-11-01")
