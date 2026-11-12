from app.services import ranking_service


def test_apelido_de_exibicao_usa_o_apelido_escolhido():
    assert ranking_service.apelido_de_exibicao("cm9x1abc", "Ana Lu") == "Ana Lu"


def test_sem_apelido_cai_num_nome_neutro_estavel():
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", None) == "Aluno K3F9"
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", "") == "Aluno K3F9"
