from app.services import ranking_service


def test_apelido_de_exibicao_usa_o_apelido_escolhido():
    assert ranking_service.apelido_de_exibicao("cm9x1abc", "Ana Lu") == "Ana Lu"


def test_apelido_vence_o_username():
    assert ranking_service.apelido_de_exibicao("cm9x1abc", "Ana Lu", "analuiza") == "Ana Lu"


def test_sem_apelido_mostra_o_username_do_cadastro():
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", None, "analuiza") == "analuiza"
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", "", "analuiza") == "analuiza"


def test_sem_apelido_e_sem_username_cai_num_nome_neutro_estavel():
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", None) == "Aluno K3F9"
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", "", None) == "Aluno K3F9"
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", None, "") == "Aluno K3F9"
