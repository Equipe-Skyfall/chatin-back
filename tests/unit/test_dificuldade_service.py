from app.services import dificuldade_service as d


def test_classificar_desempenho_baixo_medio_alto():
    assert d.classificar_desempenho(2, 10) == d.DESEMPENHO_BAIXO  # 20%
    assert d.classificar_desempenho(6, 10) == d.DESEMPENHO_MEDIO  # 60%
    assert d.classificar_desempenho(9, 10) == d.DESEMPENHO_ALTO  # 90%


def test_classificar_desempenho_limites_inclusivos_corretos():
    assert d.classificar_desempenho(5, 10) == d.DESEMPENHO_MEDIO  # exactly 50% is not baixo
    assert d.classificar_desempenho(4, 10) == d.DESEMPENHO_BAIXO  # 40%
    assert d.classificar_desempenho(8, 10) == d.DESEMPENHO_ALTO  # exactly 80% is alto


def test_classificar_desempenho_poucos_dados_e_medio():
    assert d.classificar_desempenho(0, 0) == d.DESEMPENHO_MEDIO
    assert d.classificar_desempenho(0, 4) == d.DESEMPENHO_MEDIO  # all wrong, but too few answers
    assert d.classificar_desempenho(4, 4) == d.DESEMPENHO_MEDIO


def test_taxa_acerto():
    assert d.taxa_acerto(0, 0) == 0.0
    assert d.taxa_acerto(1, 3) == 33.33


def test_nivel_para_selecao_prefere_tema_com_dados_suficientes():
    assert d.nivel_para_selecao((1, 10), 95.0) == d.NIVEL_COM_DIFICULDADE
    assert d.nivel_para_selecao((10, 10), 20.0) == d.NIVEL_INDO_BEM


def test_nivel_para_selecao_cai_para_media_global_sem_dados_no_tema():
    assert d.nivel_para_selecao(None, 95.0) == d.NIVEL_INDO_BEM
    assert d.nivel_para_selecao((0, 2), 95.0) == d.NIVEL_INDO_BEM  # too few in the tema
    assert d.nivel_para_selecao(None, None) == d.NIVEL_NEUTRO
