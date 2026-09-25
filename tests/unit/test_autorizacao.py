"""Unit tests for `app/core/autorizacao.py` - the write-access rule that
keeps the global curriculum admin-only and a student's own trilha
owner-only. There is no read-access check here (see the module docstring -
every trilha is publicly readable), so nothing to test for reads.
"""

import pytest

from app.core.autorizacao import is_admin, verificar_acesso_escrita
from app.core.exceptions import AcessoNegadoException, MateriaNaoEncontradaException
from app.core.security import TokenPayload
from app.models.materia import Materia

ADMIN = TokenPayload(user_id="admin-1", role="ADMIN")
ALUNO_DONO = TokenPayload(user_id="aluno-1", role="ALUNO")
ALUNO_OUTRO = TokenPayload(user_id="aluno-2", role="ALUNO")


def _materia(owner_user_id: str | None) -> Materia:
    materia = Materia(nome="Teste", owner_user_id=owner_user_id)
    materia.id = "materia-fake-id"
    return materia


# --- verificar_acesso_escrita ---


def test_escrita_em_conteudo_global_permite_admin():
    verificar_acesso_escrita(_materia(None), ADMIN)  # não levanta


def test_escrita_em_conteudo_global_rejeita_aluno():
    with pytest.raises(AcessoNegadoException):
        verificar_acesso_escrita(_materia(None), ALUNO_DONO)


def test_escrita_na_propria_trilha_permite_o_dono():
    verificar_acesso_escrita(_materia("aluno-1"), ALUNO_DONO)  # não levanta


def test_escrita_na_trilha_de_outro_aluno_levanta_nao_encontrada_nao_negado():
    """404, não 403 - uma trilha de outro aluno nunca confirma pra quem
    pergunta que o id pertence a alguém (ver docstring de
    `verificar_acesso_escrita`)."""
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_escrita(_materia("aluno-1"), ALUNO_OUTRO)


def test_admin_nao_tem_acesso_especial_a_trilha_de_aluno():
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_escrita(_materia("aluno-1"), ADMIN)


# --- is_admin ---


def test_is_admin():
    assert is_admin(ADMIN) is True
    assert is_admin(ALUNO_DONO) is False
