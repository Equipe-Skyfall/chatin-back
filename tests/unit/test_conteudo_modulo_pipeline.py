import uuid

import pytest

from app.core.exceptions import ConteudoIndisponivelException, GeracaoConteudoFalhouException
from app.models.fonte import Fonte
from app.models.modulo import STATUS_ERRO
from app.services.conteudo_modulo_pipeline import gerar_conteudo_modulo
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder
from tests.fakes.in_memory_repositories import InMemoryModuloRepository


def _tema_com_fontes():
    tema = TemaBuilder().pronto().build()
    tema.fontes = [
        Fonte(
            id=uuid.uuid4(),
            tema_id=tema.id,
            conteudo_extraido="Conteúdo da fonte.",
            tipo="busca_automatica",
        )
    ]
    return tema


def test_gera_conteudo_do_modulo_uma_unica_chamada_de_ia(fake_ai_provider):
    tema = _tema_com_fontes()
    modulo = ModuloBuilder().com_tema_id(tema.id).com_conteudo(None).build()
    modulo_repo = InMemoryModuloRepository()

    gerar_conteudo_modulo(modulo, tema, modulo_repo, fake_ai_provider)

    assert fake_ai_provider.gerar_conteudo_modulo_calls == 1
    assert modulo.conteudo is not None
    assert modulo.titulo in modulo.conteudo or "Conteúdo de teste" in modulo.conteudo


def test_tema_sem_fontes_levanta_excecao(fake_ai_provider):
    tema = TemaBuilder().pronto().build()
    tema.fontes = []
    modulo = ModuloBuilder().com_tema_id(tema.id).com_conteudo(None).build()
    modulo_repo = InMemoryModuloRepository()

    with pytest.raises(ConteudoIndisponivelException):
        gerar_conteudo_modulo(modulo, tema, modulo_repo, fake_ai_provider)

    assert fake_ai_provider.gerar_conteudo_modulo_calls == 0


def test_falha_do_provedor_marca_modulo_como_erro(fake_ai_provider):
    fake_ai_provider.falhar_gerar_conteudo_modulo = True
    tema = _tema_com_fontes()
    modulo = ModuloBuilder().com_tema_id(tema.id).com_conteudo(None).build()
    modulo_repo = InMemoryModuloRepository()

    with pytest.raises(GeracaoConteudoFalhouException):
        gerar_conteudo_modulo(modulo, tema, modulo_repo, fake_ai_provider)

    assert modulo.status == STATUS_ERRO
