import uuid
from datetime import UTC, datetime, timedelta

from app.schemas.progresso import (
    DesempenhoTemaOut,
    ProgressoMateriaOut,
    ProgressoModuloOut,
    ProgressoOut,
    ProgressoTemaOut,
)
from app.services.recomendacao_service import recomendar_proximos_estudos

AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _modulo(titulo="Módulo", estado="disponivel", tentativas=0):
    return ProgressoModuloOut(
        modulo_id=uuid.uuid4(),
        titulo=titulo,
        estado=estado,
        melhor_pontuacao=None,
        tentativas_count=tentativas,
    )


def _tema(modulos, taxa=0.0, respostas=0, nivel="medio", titulo="Tema"):
    return ProgressoTemaOut(
        tema_id=uuid.uuid4(),
        titulo=titulo,
        estado="disponivel",
        percentual_completo=0.0,
        desempenho=DesempenhoTemaOut(nivel=nivel, taxa_acerto=taxa, total_respostas=respostas),
        modulos=modulos,
    )


def _progresso(*temas):
    materia = ProgressoMateriaOut(
        materia_id=uuid.uuid4(),
        nome="Matéria",
        estado="disponivel",
        percentual_completo=0.0,
        xp=0,
        temas=list(temas),
    )
    return ProgressoOut(materias=[materia])


def _lista(progresso, ultimo=None, limite=5):
    return recomendar_proximos_estudos(progresso, ultimo or {}, limite, AGORA)


def _recomendar(progresso, ultimo=None):
    """The top recommendation, or None - what most rules are checked against."""
    lista = _lista(progresso, ultimo)
    return lista[0] if lista else None


def test_sem_modulo_aberto_nao_recomenda_nada():
    assert _recomendar(_progresso()) is None
    assert _recomendar(_progresso(_tema([_modulo(estado="bloqueado")]))) is None


def test_modulo_bloqueado_nunca_e_recomendado():
    bloqueado = _modulo("Bloqueado", estado="bloqueado")
    aberto = _modulo("Aberto")

    recomendacao = _recomendar(_progresso(_tema([bloqueado, aberto])))

    assert recomendacao.modulo_id == aberto.modulo_id


def test_conteudo_novo_e_recomendado_quando_nao_ha_historico():
    primeiro, segundo = _modulo("Primeiro"), _modulo("Segundo")

    recomendacao = _recomendar(_progresso(_tema([primeiro, segundo])))

    assert recomendacao.modulo_id == primeiro.modulo_id  # ties keep the trail's order
    assert recomendacao.motivo == "nao_estudado"
    assert recomendacao.dias_desde_ultimo_estudo is None
    assert recomendacao.taxa_acerto_tema is None


def test_baixo_desempenho_vence_conteudo_novo():
    fraco = _modulo("Fraco", estado="concluido", tentativas=1)
    novo = _modulo("Novo")
    progresso = _progresso(
        _tema([fraco], taxa=20.0, respostas=10, nivel="baixo", titulo="Fraco"),
        _tema([novo]),
    )

    recomendacao = _recomendar(progresso, {fraco.modulo_id: AGORA - timedelta(days=1)})

    assert recomendacao.modulo_id == fraco.modulo_id
    assert recomendacao.motivo == "baixo_desempenho"
    assert recomendacao.taxa_acerto_tema == 20.0


def test_conteudo_novo_vence_modulo_forte_estudado_ha_pouco():
    forte = _modulo("Forte", estado="concluido", tentativas=2)
    novo = _modulo("Novo")
    progresso = _progresso(
        _tema([forte], taxa=95.0, respostas=20, nivel="alto"),
        _tema([novo]),
    )

    recomendacao = _recomendar(progresso, {forte.modulo_id: AGORA - timedelta(days=1)})

    assert recomendacao.modulo_id == novo.modulo_id
    assert recomendacao.motivo == "nao_estudado"


def test_revisao_espacada_traz_de_volta_um_modulo_forte_depois_de_muito_tempo():
    forte = _modulo("Forte", estado="concluido", tentativas=2)
    novo = _modulo("Novo")
    progresso = _progresso(
        _tema([forte], taxa=90.0, respostas=20, nivel="alto"),
        _tema([novo]),
    )

    recomendacao = _recomendar(progresso, {forte.modulo_id: AGORA - timedelta(days=30)})

    assert recomendacao.modulo_id == forte.modulo_id
    assert recomendacao.motivo == "revisao_espacada"
    assert recomendacao.dias_desde_ultimo_estudo == 30


def test_mais_tempo_desde_o_estudo_aumenta_a_prioridade():
    antigo = _modulo("Antigo", estado="concluido", tentativas=1)
    recente = _modulo("Recente", estado="concluido", tentativas=1)
    progresso = _progresso(
        _tema([recente], taxa=60.0, respostas=10),
        _tema([antigo], taxa=60.0, respostas=10),
    )

    recomendacao = _recomendar(
        progresso,
        {
            recente.modulo_id: AGORA - timedelta(hours=6),
            antigo.modulo_id: AGORA - timedelta(days=3),
        },
    )

    assert recomendacao.modulo_id == antigo.modulo_id


def test_aluno_fraco_volta_mais_cedo_que_aluno_forte():
    """Same time since the last study: the weaker tema is due sooner."""
    fraco = _modulo("Fraco", estado="concluido", tentativas=1)
    forte = _modulo("Forte", estado="concluido", tentativas=1)
    progresso = _progresso(
        _tema([forte], taxa=90.0, respostas=10, nivel="alto"),
        _tema([fraco], taxa=30.0, respostas=10, nivel="baixo"),
    )
    ha_um_dia = AGORA - timedelta(days=1)

    recomendacao = _recomendar(progresso, {fraco.modulo_id: ha_um_dia, forte.modulo_id: ha_um_dia})

    assert recomendacao.modulo_id == fraco.modulo_id


def test_poucas_respostas_nao_contam_como_desempenho_baixo():
    """A tema with 2 answers (both wrong) is still the neutral cold start."""
    poucos = _modulo("Poucos", estado="concluido", tentativas=1)
    novo = _modulo("Novo")
    progresso = _progresso(
        _tema([poucos], taxa=0.0, respostas=2, nivel="medio"),
        _tema([novo]),
    )

    recomendacao = _recomendar(progresso, {poucos.modulo_id: AGORA - timedelta(hours=1)})

    assert recomendacao.modulo_id == novo.modulo_id


def test_modulo_concluido_sem_data_conta_como_vencido():
    antigo = _modulo("Antigo", estado="concluido", tentativas=1)

    recomendacao = _recomendar(_progresso(_tema([antigo], taxa=50.0, respostas=10)))

    assert recomendacao.modulo_id == antigo.modulo_id
    assert recomendacao.ultimo_estudo is None
    assert recomendacao.dias_desde_ultimo_estudo is None


def test_recomenda_algo_mesmo_quando_tudo_esta_em_dia():
    unico = _modulo("Único", estado="concluido", tentativas=3)

    recomendacao = _recomendar(
        _progresso(_tema([unico], taxa=100.0, respostas=30, nivel="alto")),
        {unico.modulo_id: AGORA},
    )

    assert recomendacao.modulo_id == unico.modulo_id


def test_modulo_fraco_estudado_ha_pouco_nao_volta_na_hora():
    """Spaced repetition: even a weak tema waits before coming back."""
    fraco = _modulo("Fraco", estado="concluido", tentativas=1)
    novo = _modulo("Novo")
    progresso = _progresso(
        _tema([fraco], taxa=20.0, respostas=10, nivel="baixo"),
        _tema([novo]),
    )

    recomendacao = _recomendar(progresso, {fraco.modulo_id: AGORA - timedelta(hours=2)})

    assert recomendacao.modulo_id == novo.modulo_id


def test_lista_vem_da_mais_urgente_para_a_menos_com_posicao():
    fraco = _modulo("Fraco", estado="concluido", tentativas=1)
    novo = _modulo("Novo")
    forte = _modulo("Forte", estado="concluido", tentativas=1)
    progresso = _progresso(
        _tema([forte], taxa=95.0, respostas=20, nivel="alto"),
        _tema([novo]),
        _tema([fraco], taxa=20.0, respostas=10, nivel="baixo"),
    )
    ontem = AGORA - timedelta(days=1)

    lista = _lista(progresso, {fraco.modulo_id: ontem, forte.modulo_id: ontem})

    assert [r.modulo_id for r in lista] == [fraco.modulo_id, novo.modulo_id, forte.modulo_id]
    assert [r.posicao for r in lista] == [1, 2, 3]
    prioridades = [r.prioridade for r in lista]
    assert prioridades == sorted(prioridades, reverse=True)


def test_lista_respeita_o_limite():
    modulos = [_modulo(f"M{i}") for i in range(8)]
    progresso = _progresso(_tema(modulos))

    assert len(_lista(progresso)) == 5
    assert len(_lista(progresso, limite=3)) == 3
    assert len(_lista(progresso, limite=20)) == 8
    assert _lista(progresso, limite=0) == []


def test_lista_vazia_sem_modulo_aberto():
    assert _lista(_progresso()) == []
    assert _lista(_progresso(_tema([_modulo(estado="bloqueado")]))) == []


def test_empates_mantem_a_ordem_da_trilha():
    primeiro, segundo, terceiro = _modulo("A"), _modulo("B"), _modulo("C")

    lista = _lista(_progresso(_tema([primeiro, segundo, terceiro])))

    assert [r.modulo_id for r in lista] == [
        primeiro.modulo_id,
        segundo.modulo_id,
        terceiro.modulo_id,
    ]
