"""Runs the real pipelines + repositories against a real Postgres schema.
Requires TEST_DATABASE_URL (see tests/integration/conftest.py) - skipped otherwise.
"""

import pytest

from app.core.exceptions import ConteudoIndisponivelException, GeracaoConteudoFalhouException
from app.models.materia import Materia
from app.models.modulo import STATUS_GERANDO as MODULO_STATUS_GERANDO
from app.models.modulo import STATUS_PRONTO as MODULO_STATUS_PRONTO
from app.models.modulo import Modulo
from app.models.tema import STATUS_GERANDO as TEMA_STATUS_GERANDO
from app.models.tema import STATUS_PRONTO as TEMA_STATUS_PRONTO
from app.models.tema import Tema
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tema_repository import TemaRepository
from app.services.conteudo_modulo_pipeline import gerar_conteudo_modulo
from app.services.fonte_pipeline import buscar_fontes_tema
from app.services.questionario_pipeline import gerar_questionario_modulo
from tests.fakes.fake_ai_provider import FakeAIProvider


def test_criar_tema_busca_fontes_com_sucesso(db_session):
    tema_repo = TemaRepository(db_session)
    ai_provider = FakeAIProvider()

    materia = Materia(nome="História")
    db_session.add(materia)
    db_session.commit()

    tema = Tema(
        materia_id=materia.id, titulo="Revolução Francesa", ordem=0, status=TEMA_STATUS_GERANDO
    )
    tema_repo.add(tema)
    tema_repo.commit()
    tema_repo.refresh(tema)

    buscar_fontes_tema(tema, tema_repo, ai_provider)

    assert tema.status == TEMA_STATUS_PRONTO
    assert len(tema.fontes) > 0
    assert ai_provider.buscar_fontes_calls == 1


def test_criar_tema_com_falha_marca_status_erro(db_session):
    tema_repo = TemaRepository(db_session)
    ai_provider = FakeAIProvider()
    ai_provider.falhar_buscar_fontes = True

    materia = Materia(nome="Matemática")
    db_session.add(materia)
    db_session.commit()

    tema = Tema(materia_id=materia.id, titulo="Funções", ordem=0, status=TEMA_STATUS_GERANDO)
    tema_repo.add(tema)
    tema_repo.commit()
    tema_repo.refresh(tema)

    try:
        buscar_fontes_tema(tema, tema_repo, ai_provider)
    except GeracaoConteudoFalhouException:
        pass

    db_session.refresh(tema)
    assert tema.status == "erro"


def test_criar_modulo_gera_conteudo_e_pool_de_questoes(db_session):
    tema_repo = TemaRepository(db_session)
    modulo_repo = ModuloRepository(db_session)
    questionario_repo = QuestionarioRepository(db_session)
    ai_provider = FakeAIProvider()

    materia = Materia(nome="Química")
    db_session.add(materia)
    db_session.commit()

    tema = Tema(materia_id=materia.id, titulo="Estequiometria", ordem=0, status=TEMA_STATUS_GERANDO)
    tema_repo.add(tema)
    tema_repo.commit()
    tema_repo.refresh(tema)
    buscar_fontes_tema(tema, tema_repo, ai_provider)
    tema = tema_repo.get_with_relations(tema.id)

    modulo = Modulo(tema_id=tema.id, titulo="Parte 1", ordem=0, status=MODULO_STATUS_GERANDO)
    modulo_repo.add(modulo)
    modulo_repo.commit()
    modulo_repo.refresh(modulo)

    gerar_conteudo_modulo(modulo, tema, modulo_repo, ai_provider)
    assert modulo.conteudo is not None

    gerar_questionario_modulo(modulo, questionario_repo, modulo_repo, ai_provider, pool_size=12)

    assert modulo.status == MODULO_STATUS_PRONTO
    questionario = questionario_repo.get_by_modulo(modulo.id)
    assert questionario is not None
    pool_ids = questionario_repo.get_questao_ids_pool(questionario.id)
    assert len(pool_ids) == 12
    assert len(questionario_repo.get_gabarito_map(pool_ids)) == 12


def test_criar_modulo_antes_do_tema_ter_fontes_falha(db_session):
    tema_repo = TemaRepository(db_session)
    modulo_repo = ModuloRepository(db_session)
    ai_provider = FakeAIProvider()

    materia = Materia(nome="Física")
    db_session.add(materia)
    db_session.commit()

    tema = Tema(materia_id=materia.id, titulo="Cinemática", ordem=0, status=TEMA_STATUS_GERANDO)
    tema_repo.add(tema)
    tema_repo.commit()
    tema_repo.refresh(tema)
    # deliberately NOT searching fontes - tema.fontes stays empty

    modulo = Modulo(tema_id=tema.id, titulo="Parte 1", ordem=0, status=MODULO_STATUS_GERANDO)
    modulo_repo.add(modulo)
    modulo_repo.commit()
    modulo_repo.refresh(modulo)

    with pytest.raises(ConteudoIndisponivelException):
        gerar_conteudo_modulo(modulo, tema, modulo_repo, ai_provider)
