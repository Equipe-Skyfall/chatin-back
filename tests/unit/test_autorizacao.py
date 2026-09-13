"""Unit tests for `app/core/autorizacao.py` - the ownership matrix that keeps
a student's personal trilha private (and keeps admin-only mutation of the
global curriculum unchanged) once `Materia.owner_user_id` exists."""

import uuid

import pytest

from app.core.autorizacao import is_admin, verificar_acesso_escrita, verificar_acesso_leitura
from app.core.exceptions import AcessoNegadoException, MateriaNaoEncontradaException
from app.core.security import TokenPayload
from app.models.materia import Materia

ADMIN = TokenPayload(user_id="admin-1", role="ADMIN")
ALUNO_DONO = TokenPayload(user_id="aluno-1", role="USER")
ALUNO_OUTRO = TokenPayload(user_id="aluno-2", role="USER")


def _materia(owner_user_id: str | None) -> Materia:
    materia = Materia(nome="Teste", owner_user_id=owner_user_id)
    materia.id = uuid.uuid4()
    return materia


# --- leitura ---


def test_leitura_de_materia_global_e_livre_para_qualquer_autenticado():
    materia = _materia(None)
    verificar_acesso_leitura(materia, ADMIN)
    verificar_acesso_leitura(materia, ALUNO_DONO)
    verificar_acesso_leitura(materia, ALUNO_OUTRO)


def test_leitura_de_trilha_pessoal_e_livre_para_o_dono():
    materia = _materia("aluno-1")
    verificar_acesso_leitura(materia, ALUNO_DONO)


def test_leitura_de_trilha_pessoal_e_negada_a_outro_usuario():
    materia = _materia("aluno-1")
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_leitura(materia, ALUNO_OUTRO)


def test_leitura_de_trilha_pessoal_e_negada_ao_admin():
    """Admin não tem acesso especial à trilha privada de um aluno."""
    materia = _materia("aluno-1")
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_leitura(materia, ADMIN)


# --- escrita ---


def test_escrita_em_materia_global_exige_admin():
    materia = _materia(None)
    verificar_acesso_escrita(materia, ADMIN)
    with pytest.raises(AcessoNegadoException):
        verificar_acesso_escrita(materia, ALUNO_DONO)


def test_escrita_em_trilha_pessoal_e_livre_para_o_dono():
    materia = _materia("aluno-1")
    verificar_acesso_escrita(materia, ALUNO_DONO)


def test_escrita_em_trilha_pessoal_e_negada_a_outro_usuario():
    materia = _materia("aluno-1")
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_escrita(materia, ALUNO_OUTRO)


def test_escrita_em_trilha_pessoal_e_negada_ao_admin():
    materia = _materia("aluno-1")
    with pytest.raises(MateriaNaoEncontradaException):
        verificar_acesso_escrita(materia, ADMIN)


# --- is_admin ---


def test_is_admin():
    assert is_admin(ADMIN) is True
    assert is_admin(ALUNO_DONO) is False
