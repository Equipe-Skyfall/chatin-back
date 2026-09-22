"""Unit tests for the admin agent's tools (`agent_tools.py`) that exercise
real repository methods against a plain fake - not `MagicMock`, which
silently accepts any attribute name and so never catches a tool calling a
repository method that was renamed/removed elsewhere (this is exactly how
`_listar_materias` shipped calling `.list_all()` after `MateriaRepository`
was rewritten to `.list_globais()`/`.list_publica()`/etc. - caught only by
live testing, not by the existing MagicMock-based tests).
"""

import uuid

from app.ai.schemas import FerramentaContexto
from app.models.materia import Materia
from app.services.agent_tools import executar_ferramenta


class _RealShapeMateriaRepository:
    """Only the methods `MateriaRepository` actually has today - calling
    anything else raises `AttributeError`, same as the real class would."""

    def __init__(self, materias: list[Materia]):
        self._materias = materias

    def list_globais(self) -> list[Materia]:
        return [m for m in self._materias if m.owner_user_id is None]


def _ctx(materia_repo) -> FerramentaContexto:
    return FerramentaContexto(
        materia_repo=materia_repo,
        tema_repo=None,
        modulo_repo=None,
        questionario_repo=None,
        xp_repo=None,
        progresso_repo=None,
        voto_repo=None,
        ai_provider=None,
        pool_size=12,
        user_id="admin-1",
        conversa_id=uuid.uuid4(),
    )


def test_listar_materias_usa_list_globais_e_nao_falha():
    repo = _RealShapeMateriaRepository(
        [
            Materia(id=uuid.uuid4(), nome="Matemática", owner_user_id=None),
            Materia(id=uuid.uuid4(), nome="Trilha de um aluno", owner_user_id="aluno-1"),
        ]
    )

    resultado = executar_ferramenta("listar_materias", {}, _ctx(repo))

    assert "Matemática" in resultado
    assert "Erro" not in resultado


def test_listar_materias_sem_materias():
    resultado = executar_ferramenta("listar_materias", {}, _ctx(_RealShapeMateriaRepository([])))
    assert "Nenhuma matéria" in resultado
