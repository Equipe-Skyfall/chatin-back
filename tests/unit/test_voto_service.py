import uuid

import pytest

from app.core.exceptions import MateriaNaoEncontradaException, VotoEmConteudoGlobalException
from app.models.materia import Materia
from app.models.voto_materia import VotoMateria
from app.services import voto_service


class _FakeMateriaRepository:
    def __init__(self, materias: dict[uuid.UUID, Materia]):
        self._materias = materias

    def get(self, materia_id: uuid.UUID) -> Materia | None:
        return self._materias.get(materia_id)


class _FakeVotoRepository:
    def __init__(self):
        self._votos: dict[tuple[str, uuid.UUID], VotoMateria] = {}
        self.commits = 0

    def get_by_user_e_materia(self, user_id: str, materia_id: uuid.UUID) -> VotoMateria | None:
        return self._votos.get((user_id, materia_id))

    def add(self, voto: VotoMateria) -> VotoMateria:
        self._votos[(voto.user_id, voto.materia_id)] = voto
        return voto

    def delete(self, voto: VotoMateria) -> None:
        self._votos.pop((voto.user_id, voto.materia_id), None)

    def commit(self) -> None:
        self.commits += 1

    def scores_por_materias(self, materia_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        scores: dict[uuid.UUID, int] = {}
        for voto in self._votos.values():
            if voto.materia_id in materia_ids:
                scores[voto.materia_id] = scores.get(voto.materia_id, 0) + voto.valor
        return scores


def _materia(owner_user_id: str | None) -> Materia:
    materia = Materia(nome="Teste", owner_user_id=owner_user_id)
    materia.id = uuid.uuid4()
    return materia


def test_votar_em_trilha_de_aluno_retorna_score():
    materia = _materia("aluno-1")
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()

    score = voto_service.votar("aluno-2", materia.id, 1, materia_repo, voto_repo)

    assert score == 1


def test_votar_de_novo_atualiza_em_vez_de_somar():
    materia = _materia("aluno-1")
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()

    voto_service.votar("aluno-2", materia.id, 1, materia_repo, voto_repo)
    score = voto_service.votar("aluno-2", materia.id, -1, materia_repo, voto_repo)

    assert score == -1


def test_votos_de_alunos_diferentes_somam():
    materia = _materia("aluno-1")
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()

    voto_service.votar("aluno-2", materia.id, 1, materia_repo, voto_repo)
    score = voto_service.votar("aluno-3", materia.id, 1, materia_repo, voto_repo)

    assert score == 2


def test_votar_em_conteudo_global_levanta_excecao():
    materia = _materia(None)
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()

    with pytest.raises(VotoEmConteudoGlobalException):
        voto_service.votar("aluno-1", materia.id, 1, materia_repo, voto_repo)


def test_votar_em_materia_inexistente_levanta_excecao():
    materia_repo = _FakeMateriaRepository({})
    voto_repo = _FakeVotoRepository()

    with pytest.raises(MateriaNaoEncontradaException):
        voto_service.votar("aluno-1", uuid.uuid4(), 1, materia_repo, voto_repo)


def test_remover_voto_volta_o_score_a_zero():
    materia = _materia("aluno-1")
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()
    voto_service.votar("aluno-2", materia.id, 1, materia_repo, voto_repo)

    score = voto_service.remover_voto("aluno-2", materia.id, materia_repo, voto_repo)

    assert score == 0


def test_remover_voto_inexistente_nao_falha():
    materia = _materia("aluno-1")
    materia_repo = _FakeMateriaRepository({materia.id: materia})
    voto_repo = _FakeVotoRepository()

    score = voto_service.remover_voto("aluno-2", materia.id, materia_repo, voto_repo)

    assert score == 0
