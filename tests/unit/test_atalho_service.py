import uuid

from app.ai.schemas import FerramentaContexto
from app.models.materia import Materia
from app.models.modulo import Modulo
from app.models.tema import Tema
from app.services import atalho_service

USER = "aluno-1"


class _MateriaRepo:
    def __init__(self, *materias):
        self._materias = list(materias)

    def list_minhas_e_globais_with_temas_e_modulos(self, user_id):
        return self._materias

    list_minhas_e_globais = list_minhas_e_globais_with_temas_e_modulos


class _ProgressoRepo:
    def list_by_user_and_modulos(self, user_id, modulo_ids):
        return []


class _TentativaRepo:
    def __init__(self, por_tema=None):
        self._por_tema = por_tema or {}

    def desempenho_por_tema(self, user_id):
        return dict(self._por_tema)

    def ultimo_estudo_por_modulo(self, user_id):
        return {}


class _XpRepo:
    def __init__(self, total=0, ranking=None):
        self._total = total
        self._ranking = ranking or []

    def total_por_usuario(self, user_id):
        return self._total

    def total_por_usuario_e_materia(self, user_id, materia_id):
        return 0

    def ranking_global(self, limit=20):
        return self._ranking[:limit]


class _PerfilRepo:
    def __init__(self, nomes=None):
        self._nomes = nomes or {}

    def nomes_por_ids(self, ids):
        return {i: self._nomes[i] for i in ids if i in self._nomes}


def _ctx(materia_repo=None, xp_repo=None, tentativa_repo=None):
    return FerramentaContexto(
        materia_repo=materia_repo or _MateriaRepo(),
        tema_repo=None,
        modulo_repo=None,
        questionario_repo=None,
        xp_repo=xp_repo or _XpRepo(),
        progresso_repo=_ProgressoRepo(),
        tentativa_repo=tentativa_repo or _TentativaRepo(),
        voto_repo=None,
        ai_provider=None,
        pool_size=12,
        user_id=USER,
        conversa_id=uuid.uuid4(),
    )


def _materia_com_tema_e_modulo():
    materia = Materia(id=uuid.uuid4(), nome="Matemática", owner_user_id=None)
    tema = Tema(id=uuid.uuid4(), materia_id=materia.id, titulo="Funções", ordem=0, status="pronto")
    tema.modulos = [
        Modulo(id=uuid.uuid4(), tema_id=tema.id, titulo="Função afim", ordem=0, status="pronto")
    ]
    materia.temas = [tema]
    return materia, tema


def _atalho(mensagem, ctx=None, perfil_repo=None):
    return atalho_service.tentar_atalho(mensagem, ctx or _ctx(), perfil_repo or _PerfilRepo())


# --- what goes to the agent ---


def test_mensagem_que_nao_e_um_pedido_conhecido_vai_para_o_agente():
    assert _atalho("explique a revolução francesa") is None
    assert _atalho("o que é desempenho em física?") is None
    assert _atalho("oi") is None


# --- desempenho ---


def test_desempenho_sem_progresso_fala_com_o_aluno():
    resposta = _atalho("como estou indo?")

    assert resposta == "Você ainda não tem nenhum progresso registrado."


def test_desempenho_lista_o_nivel_por_tema_e_explica_os_niveis_ao_aluno():
    materia, tema = _materia_com_tema_e_modulo()
    ctx = _ctx(_MateriaRepo(materia), tentativa_repo=_TentativaRepo({tema.id: (2, 10)}))

    resposta = _atalho("meu desempenho", ctx)

    assert resposta.startswith("Aqui está o seu desempenho:")
    assert "Funções baixo (20% de 10 respostas)" in resposta
    assert "Níveis por tema: baixo = menos de 50% de acerto" in resposta
    assert "o aluno" not in resposta.lower()  # addressed to the student, not the model


# --- proximos estudos ---


def test_proximos_estudos_lista_o_modulo_liberado_com_o_motivo():
    materia, _ = _materia_com_tema_e_modulo()

    resposta = _atalho("o que devo estudar agora", _ctx(_MateriaRepo(materia)))

    assert resposta.startswith("Estes são os módulos que recomendo")
    assert "1. Função afim (Matemática > Funções" in resposta
    assert "ainda não estudou" in resposta


def test_proximos_estudos_sem_nada_liberado():
    resposta = _atalho("o que estudar hoje")

    assert resposta == "No momento não há nenhum módulo liberado para você estudar."


# --- xp ---


def test_xp_informa_total_nivel_e_o_que_falta():
    resposta = _atalho("quanto xp eu tenho", _ctx(xp_repo=_XpRepo(total=620)))

    assert resposta == "Você tem 620 XP e está no nível 2. Faltam 100 XP para o nível 3."


def test_xp_de_quem_ainda_nao_tem_nivel():
    resposta = _atalho("meu xp", _ctx(xp_repo=_XpRepo(total=40)))

    assert resposta == "Você tem 40 XP e ainda não chegou ao nível 1. Faltam 460 XP para o nível 1."


# --- ranking ---


def test_ranking_mostra_o_topo_com_nomes_e_a_posicao_do_aluno():
    ranking = [("a", 900), ("b", 800), (USER, 700), ("d", 600)]
    perfil = _PerfilRepo({"a": "Ana", "b": "Bruno", USER: "Eu"})

    resposta = _atalho("ver o ranking", _ctx(xp_repo=_XpRepo(ranking=ranking)), perfil)

    assert resposta.splitlines() == [
        "Ranking geral de XP:",
        "1. Ana - 900 XP",
        "2. Bruno - 800 XP",
        "3. Eu - 700 XP",
        "4. Aluno - 600 XP",  # no name known for this one
        "Sua posição: 3º, com 700 XP.",
    ]


def test_ranking_limita_o_topo_a_cinco_e_avisa_quando_o_aluno_nao_esta_nele():
    ranking = [(f"u{i}", 1000 - i) for i in range(8)]

    resposta = _atalho("qual a minha posição no ranking", _ctx(xp_repo=_XpRepo(ranking=ranking)))

    linhas = resposta.splitlines()
    assert len(linhas) == 1 + 5 + 1
    assert linhas[-1] == "Você ainda não está entre os 100 primeiros do ranking."


def test_ranking_vazio():
    assert _atalho("mostre o ranking") == "Ainda ninguém tem XP no ranking."
