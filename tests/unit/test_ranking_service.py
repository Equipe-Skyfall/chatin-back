from app.services import ranking_service


def test_apelido_de_exibicao_usa_o_apelido_escolhido():
    assert ranking_service.apelido_de_exibicao("cm9x1abc", "Ana Lu") == "Ana Lu"


def test_sem_apelido_cai_num_nome_neutro_estavel():
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", None) == "Aluno K3F9"
    assert ranking_service.apelido_de_exibicao("cm9x1k3f9", "") == "Aluno K3F9"


def test_ranking_mostra_so_apelido_posicao_e_xp_e_marca_o_proprio_aluno():
    out = ranking_service.montar_ranking(
        [("u1", 900), ("eu", 700)],
        {"u1": "Bruno", "eu": "Ana"},
        "eu",
        (2, 700),
    )

    assert [(e.posicao, e.apelido, e.xp, e.eu) for e in out.entradas] == [
        (1, "Bruno", 900, False),
        (2, "Ana", 700, True),
    ]
    assert set(out.entradas[0].model_dump()) == {"posicao", "apelido", "xp", "eu"}


def test_posicao_do_aluno_fora_do_topo_vem_em_minha_posicao():
    out = ranking_service.montar_ranking([("u1", 900)], {"u1": "Bruno"}, "eu", (57, 12))

    assert [e.eu for e in out.entradas] == [False]
    assert out.minha_posicao is not None
    assert (out.minha_posicao.posicao, out.minha_posicao.xp, out.minha_posicao.eu) == (57, 12, True)


def test_aluno_sem_xp_nao_tem_minha_posicao():
    out = ranking_service.montar_ranking([("u1", 900)], {}, "eu", None)

    assert out.minha_posicao is None
