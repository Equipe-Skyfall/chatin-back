import pytest

from app.services import intencao_service as svc
from app.services.intencao_service import ClassificadorDeIntencao, avaliar

D, P, X, R = (
    svc.INTENCAO_DESEMPENHO,
    svc.INTENCAO_PROXIMOS_ESTUDOS,
    svc.INTENCAO_XP,
    svc.INTENCAO_RANKING,
)

# Messages written apart from the examples. `None` = must reach the agent.
CASOS: list[tuple[str, str | None]] = [
    # desempenho
    ("Como estou indo?", D),
    ("como anda meu desempenho", D),
    ("me mostra meu desempenho", D),
    ("quero saber como estou nos estudos", D),
    ("qual minha taxa de acerto", D),
    ("em que tema eu tenho mais dificuldade", D),
    ("como está o meu progresso", D),
    # proximos estudos
    ("o que eu devo estudar agora?", P),
    ("o que estudar hoje", P),
    ("por onde eu continuo", P),
    ("qual o próximo módulo", P),
    ("o que eu preciso revisar?", P),
    ("me recomenda o que estudar", P),
    # xp
    ("quanto xp eu tenho?", X),
    ("qual meu nível", X),
    ("quanto falta pro próximo nível", X),
    ("quantos pontos de xp tenho", X),
    # ranking
    ("qual a minha posição no ranking", R),
    ("quero ver o ranking", R),
    ("quem lidera o ranking", R),
    # must NOT be shortcut: subject questions that reuse the same words
    ("o que é desempenho em física?", None),
    ("explique a revolução francesa", None),
    ("o que estudar para a prova de química orgânica amanhã sobre ácidos e bases", None),
    ("como melhorar meu desempenho em redação", None),
    ("quanto é 15 por cento de 80", None),
    ("o que significa nível do mar", None),
    ("qual a posição do sol ao meio dia", None),
    ("me explique o que é xp em jogos", None),
    # negation and mixed requests
    ("não quero ver meu desempenho", None),
    ("nunca me mostre o ranking", None),
    ("meu desempenho e o que estudar", None),
    # smalltalk
    ("oi", None),
    ("obrigado", None),
    ("tudo bem?", None),
    ("", None),
    ("   ", None),
]


@pytest.fixture(scope="module")
def classificador():
    return ClassificadorDeIntencao()


def test_nenhum_atalho_errado_no_conjunto_de_avaliacao(classificador):
    """Precision is what matters: a wrong shortcut answers the wrong thing, a
    missed one only costs a normal agent turn."""
    metricas = avaliar(CASOS, classificador)

    for intencao, m in metricas.items():
        assert m["precisao"] == 1.0, (intencao, m)


def test_a_maioria_dos_pedidos_validos_vira_atalho(classificador):
    """Recall is the softer goal: the misses are words the examples never use
    (a plain bag of words can't relate "lidera" to "liderando"), and each one
    just goes to the agent."""
    metricas = avaliar(CASOS, classificador)

    for intencao in (D, P, X, R):
        assert metricas[intencao]["recall"] >= 0.6, (intencao, metricas[intencao])
    media = sum(m["recall"] for m in metricas.values()) / len(metricas)
    assert media >= 0.85


@pytest.mark.parametrize("mensagem, esperada", [c for c in CASOS if c[1] is not None])
def test_pedido_valido_recebe_a_intencao_certa_ou_vai_pro_agente(classificador, mensagem, esperada):
    resultado = classificador.classificar(mensagem)

    assert resultado is None or resultado.intencao == esperada


def test_ordem_das_palavras_so_importa_com_bigramas():
    exemplos = {"a": ["quero ver o ranking"], "b": ["ranking quero ver"]}
    kwargs = {"margem": 0.0, "cobertura": 0.0}
    sem_ordem = ClassificadorDeIntencao(exemplos, ngramas=(1, 1), **kwargs)
    com_ordem = ClassificadorDeIntencao(exemplos, ngramas=(1, 2), **kwargs)

    pontos = sem_ordem.pontuacoes("quero ver o ranking")
    assert pontos["a"] == pytest.approx(pontos["b"])  # same bag of words: indistinguishable
    pontos = com_ordem.pontuacoes("quero ver o ranking")
    assert pontos["a"] > pontos["b"]


def test_mensagem_vazia_ou_sem_palavras_conhecidas_nao_vira_atalho(classificador):
    assert classificador.classificar("") is None
    assert classificador.classificar("???") is None
    assert classificador.classificar("blá blá blá") is None


def test_pontuacao_e_devolvida_com_a_intencao(classificador):
    resultado = classificador.classificar("como estou indo")

    assert resultado.intencao == D
    assert 0.5 <= resultado.pontuacao <= 1.0


def test_classificador_padrao_e_reutilizado():
    assert svc.classificador_padrao() is svc.classificador_padrao()
    assert svc.classificar_intencao("meu xp").intencao == X
