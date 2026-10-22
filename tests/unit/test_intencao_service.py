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


# Held out from the training data; used to pick the thresholds.
CASOS_RESERVA_C: list[tuple[str, str | None]] = [
    ("como está o meu rendimento nas questões", D),
    ("me diz quanto eu estou acertando", D),
    ("estou progredindo nos estudos", D),
    ("qual meu aproveitamento geral", D),
    ("quais assuntos eu mais erro", D),
    ("como tá meu desempenho hoje", D),
    ("quero ver como estou indo nas matérias", D),
    ("minha pontuação média", D),
    ("em quais temas vou mal", D),
    ("fui bem nas últimas questões", D),
    ("o que eu devo estudar em seguida", P),
    ("qual módulo devo fazer agora", P),
    ("me recomenda um conteúdo para estudar hoje", P),
    ("o que posso estudar agora", P),
    ("qual é a próxima aula", P),
    ("o que eu tenho que revisar", P),
    ("por onde devo continuar a estudar", P),
    ("me mostra o que estudar a seguir", P),
    ("qual o meu próximo estudo", P),
    ("o que é melhor eu estudar hoje", P),
    ("quanto xp eu já tenho", X),
    ("qual é o meu nível agora", X),
    ("me diz meu xp total", X),
    ("falta quanto xp para o próximo nível", X),
    ("em que level eu estou", X),
    ("quantos pontos de xp me faltam", X),
    ("já subi de nível", X),
    ("quanto de experiência eu tenho", X),
    ("em que posição do ranking eu estou", R),
    ("quem ocupa o primeiro lugar", R),
    ("qual o meu lugar no ranking de xp", R),
    ("me mostra quem lidera", R),
    ("estou bem no ranking", R),
    ("quero ver a classificação dos alunos", R),
    ("quem está em segundo no ranking", R),
    ("qual minha posição entre os alunos", R),
    ("qual o desempenho do atleta nas olimpíadas", None),
    ("como melhorar meu rendimento no trabalho", None),
    ("o que devo estudar para ser médico", None),
    ("qual o próximo número primo depois de 13", None),
    ("explique o que é xp em programação extrema", None),
    ("quem lidera a pesquisa sobre vacinas", None),
    ("qual o ranking de universidades do brasil", None),
    ("me fale sobre os pontos fracos do capitalismo", None),
    ("como subir de nível em um jogo", None),
    ("qual é a posição da letra a no alfabeto", None),
    ("preciso de ajuda com equações do primeiro grau", None),
    ("explique a revolução industrial", None),
    ("qual a capital da frança", None),
    ("oi, tudo certo", None),
    ("não quero ver minha posição", None),
    ("meu desempenho e meu ranking", None),
    ("quero ver meu xp e o que devo estudar", None),
    ("quais foram os resultados da eleição de 2022", None),
    ("me ensina a calcular porcentagem de acerto em uma prova", None),
    ("como é a classificação dos triângulos", None),
]

# Held out and written before the final thresholds were chosen; run once to confirm them.
CASOS_RESERVA_D: list[tuple[str, str | None]] = [
    ("como está indo o meu estudo", D),
    ("qual meu percentual de acertos", D),
    ("em que assunto estou pior", D),
    ("me mostra minha evolução nas provas", D),
    ("como eu me saí nos quizzes", D),
    ("estou acertando bastante", D),
    ("quais conteúdos eu preciso melhorar", D),
    ("o que devo estudar primeiro hoje", P),
    ("me indica um módulo para estudar", P),
    ("qual é o próximo conteúdo para mim", P),
    ("por onde eu devo começar hoje", P),
    ("o que eu devo ver em seguida", P),
    ("tem algo para eu revisar agora", P),
    ("me sugere um assunto para estudar", P),
    ("quanto xp eu tenho agora", X),
    ("qual o meu nível atual", X),
    ("quanto falta para o nível seguinte", X),
    ("me mostra meu xp", X),
    ("quantos pontos de experiência faltam", X),
    ("em que posição eu estou no ranking", R),
    ("quem está liderando o ranking", R),
    ("me mostra os primeiros colocados", R),
    ("qual é a minha classificação", R),
    ("quem tem mais pontos", R),
    ("qual a diferença entre xp e pontos de vida em jogos", None),
    ("quem é o líder do partido", None),
    ("explique o que são níveis de energia do átomo", None),
    ("qual é o desempenho esperado de um aluno do ensino médio", None),
    ("o que estudar para a prova de geografia sobre clima", None),
    ("me fala sobre o ranking da fifa", None),
    ("como calcular o percentual de acertos de um time", None),
    ("quanto é vinte por cento de cem", None),
    ("obrigado, ajudou muito", None),
    ("por favor, resuma o capítulo sobre ditadura", None),
    ("quem foi o líder da revolução russa", None),
    ("qual a posição do planeta marte no sistema solar", None),
]

INTENCOES = (D, P, X, R)
RESERVA = CASOS_RESERVA_C + CASOS_RESERVA_D


@pytest.fixture(scope="module")
def classificador():
    return ClassificadorDeIntencao()


def _media_do_recall(metricas):
    return sum(metricas[i]["recall"] for i in INTENCOES) / len(INTENCOES)


def test_nenhum_atalho_errado_nos_conjuntos_de_avaliacao(classificador):
    """Precision is what matters: a wrong shortcut answers the wrong thing, a
    missed one only costs a normal agent turn."""
    for casos in (CASOS, CASOS_RESERVA_C, CASOS_RESERVA_D):
        for intencao, m in avaliar(casos, classificador).items():
            assert m["precisao"] == 1.0, (intencao, m)


def test_pedidos_novos_viram_atalho_com_boa_cobertura(classificador):
    """Recall on messages written apart from the training data. The misses are
    phrasings the examples never saw, and each just goes to the agent."""
    metricas = avaliar(RESERVA, classificador)

    for intencao in INTENCOES:
        assert metricas[intencao]["recall"] >= 0.1, (intencao, metricas[intencao])
    assert _media_do_recall(metricas) >= 0.45


@pytest.mark.parametrize("mensagem, esperada", [c for c in CASOS if c[1] is not None])
def test_pedido_valido_recebe_a_intencao_certa_ou_vai_pro_agente(classificador, mensagem, esperada):
    resultado = classificador.classificar(mensagem)

    assert resultado is None or resultado.intencao == esperada


@pytest.mark.parametrize("mensagem", ["meu xp e meu ranking", "como estou indo e o que estudar"])
def test_dois_pedidos_na_mesma_mensagem_vao_para_o_agente(classificador, mensagem):
    assert classificador.classificar(mensagem) is None


def test_mensagem_de_conteudo_que_reusa_as_palavras_vai_para_o_agente(classificador):
    for mensagem in (
        "quais são os pontos fortes do iluminismo",
        "qual o ranking de universidades do brasil",
        "como subir de nível em um jogo",
        "qual a classificação dos seres vivos",
    ):
        assert classificador.classificar(mensagem) is None, mensagem


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


def test_pontuacoes_sao_similaridades_por_rotulo_incluindo_nenhuma(classificador):
    pontos = classificador.pontuacoes("explique a revolução francesa")

    assert set(pontos) == {D, P, X, R, "nenhuma"}
    assert all(0.0 <= valor <= 1.0 + 1e-9 for valor in pontos.values())


def test_classificador_padrao_e_reutilizado():
    assert svc.classificador_padrao() is svc.classificador_padrao()
    assert svc.classificar_intencao("meu xp").intencao == X
