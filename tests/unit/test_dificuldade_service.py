import random
import uuid

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


# --- question difficulty, from the share of wrong answers ---


def test_classificar_questao_pela_taxa_de_erro():
    assert d.classificar(0.0) == d.FACIL
    assert d.classificar(0.34) == d.FACIL
    assert d.classificar(0.35) == d.MEDIO  # the lower bound belongs to the next level
    assert d.classificar(0.64) == d.MEDIO
    assert d.classificar(0.65) == d.DIFICIL
    assert d.classificar(1.0) == d.DIFICIL


class _QuestionarioRepoComEstatisticas:
    def __init__(self, estatisticas):
        self._estatisticas = estatisticas

    def estatisticas_por_questao(self, questao_ids):
        return {q: self._estatisticas[q] for q in questao_ids if q in self._estatisticas}


def test_dificuldade_por_questao_so_confia_com_respostas_suficientes():
    nova, poucas, facil, dificil = (uuid.uuid4() for _ in range(4))
    minimo = d.MINIMO_RESPOSTAS_PARA_CONFIAR
    repo = _QuestionarioRepoComEstatisticas(
        {
            poucas: (minimo - 1, 1.0),  # every answer wrong, but too few to trust
            facil: (minimo, 0.1),
            dificil: (minimo, 0.9),
        }
    )

    resultado = d.dificuldade_por_questao([nova, poucas, facil, dificil], repo)

    assert resultado == {
        nova: d.MEDIO,  # no answers at all: the cold-start default
        poucas: d.MEDIO,
        facil: d.FACIL,
        dificil: d.DIFICIL,
    }


# --- the student's general level, from the average score ---


def test_nivel_do_aluno_pela_media_de_pontuacao():
    assert d.nivel_do_aluno(None) == d.NIVEL_NEUTRO  # never completed a quiz
    assert d.nivel_do_aluno(d.LIMIAR_BAIXO - 0.01) == d.NIVEL_COM_DIFICULDADE
    assert d.nivel_do_aluno(d.LIMIAR_BAIXO) == d.NIVEL_NEUTRO
    assert d.nivel_do_aluno(d.LIMIAR_ALTO - 0.01) == d.NIVEL_NEUTRO
    assert d.nivel_do_aluno(d.LIMIAR_ALTO) == d.NIVEL_INDO_BEM


def test_pesos_empurram_a_selecao_para_o_nivel_do_aluno():
    indo_bem = d.PESOS_POR_NIVEL[d.NIVEL_INDO_BEM]
    com_dificuldade = d.PESOS_POR_NIVEL[d.NIVEL_COM_DIFICULDADE]
    neutro = d.PESOS_POR_NIVEL[d.NIVEL_NEUTRO]

    assert indo_bem[d.DIFICIL] > indo_bem[d.FACIL]
    assert com_dificuldade[d.FACIL] > com_dificuldade[d.DIFICIL]
    assert set(neutro.values()) == {1.0}


# --- weighted sampling without replacement ---


def test_amostra_ponderada_nao_repete_item_e_respeita_k():
    itens = [uuid.uuid4() for _ in range(12)]

    amostra = d.amostra_ponderada_sem_reposicao(itens, {}, 5)

    assert len(amostra) == 5
    assert len(set(amostra)) == 5
    assert set(amostra) <= set(itens)
    assert sorted(d.amostra_ponderada_sem_reposicao(itens, {}, 99)) == sorted(itens)


def test_amostra_ponderada_prefere_itens_de_maior_peso():
    random.seed(7)
    pesado, leve = uuid.uuid4(), uuid.uuid4()
    outros = [uuid.uuid4() for _ in range(8)]
    itens = [pesado, leve, *outros]
    pesos = {pesado: 50.0, leve: 0.05}

    rodadas = 300
    com_pesado = sum(
        pesado in d.amostra_ponderada_sem_reposicao(itens, pesos, 3) for _ in range(rodadas)
    )
    com_leve = sum(
        leve in d.amostra_ponderada_sem_reposicao(itens, pesos, 3) for _ in range(rodadas)
    )

    assert com_pesado > rodadas * 0.95
    assert com_leve < rodadas * 0.1
