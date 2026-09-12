import pytest
from pydantic import ValidationError

from app.schemas.questionario import AlternativaOut, QuestaoUpdate


def _alternativas(letras: str) -> list[AlternativaOut]:
    return [AlternativaOut(letra=letra, texto=f"Alternativa {letra}") for letra in letras]


def test_aceita_edicao_parcial_sem_alternativas():
    update = QuestaoUpdate(enunciado="Novo enunciado")
    assert update.alternativas is None
    assert update.enunciado == "Novo enunciado"


def test_aceita_alternativas_com_as_cinco_letras():
    update = QuestaoUpdate(alternativas=_alternativas("ABCDE"))
    assert {a.letra for a in update.alternativas} == {"A", "B", "C", "D", "E"}


def test_rejeita_alternativas_com_letra_repetida():
    with pytest.raises(ValidationError):
        QuestaoUpdate(alternativas=_alternativas("AABDE"))


def test_rejeita_menos_de_cinco_alternativas():
    with pytest.raises(ValidationError):
        QuestaoUpdate(alternativas=_alternativas("ABCD"))


def test_rejeita_mais_de_cinco_alternativas():
    with pytest.raises(ValidationError):
        QuestaoUpdate(
            alternativas=[*_alternativas("ABCDE"), AlternativaOut(letra="A", texto="dup")]
        )
