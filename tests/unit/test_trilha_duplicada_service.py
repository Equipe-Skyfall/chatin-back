"""Duplicate-trilha check: AI title cleanup + Word2Vec/cosine search on a real
in-memory sqlite-vec index. The embedder is a deterministic bag-of-words fake -
no model file, no network."""

import math
import uuid
from types import SimpleNamespace

from app.models.materia import Materia
from app.services import trilha_duplicada_service
from app.similaridade.indice import IndiceTrilhas
from tests.fakes.fake_ai_provider import FakeAIProvider

VOCAB = [
    "napoleao", "epoca", "revolucao", "francesa", "algebra", "fundamentos", "quimica", "organica",
]  # fmt: skip
CONFIG = SimpleNamespace(TRILHA_SIMILARIDADE_IGUAL=0.95, TRILHA_SIMILARIDADE_PARECIDA=0.70)


class _Embedder:
    dim = len(VOCAB)

    def __init__(self):
        self.chamadas = 0

    def vetor(self, texto):
        self.chamadas += 1
        v = [float(texto.lower().split().count(p)) for p in VOCAB]
        norma = math.sqrt(sum(x * x for x in v))
        return [x / norma for x in v] if norma else None


class _Repo:
    def __init__(self, *materias):
        self.materias = list(materias)

    def list_publica(self):
        return self.materias


def _materia(nome, descricao=None):
    return Materia(id=uuid.uuid4(), nome=nome, descricao=descricao, owner_user_id=None)


def _verificar(nome, repo, *, descricao=None, ai=None, embedder=None):
    embedder = embedder or _Embedder()
    return trilha_duplicada_service.verificar(
        nome, descricao, repo, ai or FakeAIProvider(), CONFIG, embedder, IndiceTrilhas(embedder.dim)
    )


def test_sem_modelo_a_trilha_e_nova_mas_o_titulo_ainda_e_corrigido():
    ai = FakeAIProvider()
    ai.titulo_normalizado_fixo = "Época Napoleônica"
    veredito = trilha_duplicada_service.verificar(
        "epoca napoleonica", None, _Repo(), ai, CONFIG, embedder=None
    )

    assert (veredito.status, veredito.nome_normalizado) == ("nova", "Época Napoleônica")


def test_texto_identico_e_igual():
    existente = _materia("epoca napoleao")

    veredito = _verificar("epoca napoleao", _Repo(existente, _materia("quimica organica")))

    assert veredito.status == "igual"
    assert veredito.candidatas[0].materia is existente
    assert veredito.candidatas[0].similaridade >= 0.95


def test_titulo_corrigido_pela_ia_e_o_que_entra_na_comparacao():
    ai = FakeAIProvider()
    ai.titulo_normalizado_fixo = "epoca napoleao"  # o que o aluno digitou estava errado

    veredito = _verificar("époka napoliao", _Repo(_materia("epoca napoleao")), ai=ai)

    assert veredito.status == "igual"
    assert veredito.nome_normalizado == "epoca napoleao"


def test_entre_70_e_95_oferece_as_tres_mais_proximas_em_ordem():
    repo = _Repo(
        _materia("epoca napoleao revolucao francesa"),
        _materia("napoleao revolucao"),
        _materia("napoleao"),
        _materia("napoleao epoca revolucao francesa algebra"),
        _materia("quimica organica"),
    )

    veredito = _verificar("epoca napoleao revolucao", repo)

    assert veredito.status == "parecidas"
    assert len(veredito.candidatas) == 3
    similaridades = [c.similaridade for c in veredito.candidatas]
    assert similaridades == sorted(similaridades, reverse=True)
    assert all(0.70 <= s < 0.95 for s in similaridades)


def test_assunto_diferente_e_nova():
    veredito = _verificar("fundamentos algebra", _Repo(_materia("quimica organica")))

    assert veredito.status == "nova"
    assert veredito.candidatas == []


def test_titulo_sem_nenhuma_palavra_conhecida_e_nova():
    assert _verificar("zzz", _Repo(_materia("epoca napoleao"))).status == "nova"


def test_falha_da_ia_ao_normalizar_usa_o_titulo_digitado():
    ai = FakeAIProvider()
    ai.falhar_normalizar_titulo = True

    veredito = _verificar("  epoca napoleao ", _Repo(_materia("epoca napoleao")), ai=ai)

    assert veredito.nome_normalizado == "epoca napoleao"
    assert veredito.status == "igual"


def test_indice_acompanha_o_banco_sem_reembutir_o_que_nao_mudou():
    embedder = _Embedder()
    indice = IndiceTrilhas(embedder.dim)
    napoleao, algebra = _materia("epoca napoleao"), _materia("fundamentos algebra")
    repo = _Repo(napoleao, algebra)

    def checar(nome):
        return trilha_duplicada_service.verificar(
            nome, None, repo, FakeAIProvider(), CONFIG, embedder, indice
        )

    checar("quimica")
    depois_da_carga = embedder.chamadas
    checar("quimica")
    assert embedder.chamadas == depois_da_carga + 1  # só o vetor da consulta

    repo.materias.remove(napoleao)  # excluída no banco
    assert checar("epoca napoleao").status == "nova"
    napoleao_editada = algebra
    napoleao_editada.nome = "quimica organica"  # editada no banco
    assert checar("quimica organica").status == "igual"
