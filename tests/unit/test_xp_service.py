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
