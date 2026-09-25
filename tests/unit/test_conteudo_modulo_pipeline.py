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


def test_conteudo_recebe_o_texto_uma_vez_e_com_os_nomes_das_fontes(fake_ai_provider):
    tema = TemaBuilder().pronto().build()
    tema.fontes = [
        Fonte(
            id=uuid.uuid4(),
            tema_id=tema.id,
            conteudo_extraido="Mesmo texto.",
            origem=f"https://redirect/{n}",
            metadata_={"titulo": dominio},
            tipo="busca_automatica",
        )
        for n, dominio in enumerate(["a.com", "b.com"])
    ]
    modulo = ModuloBuilder().com_tema_id(tema.id).com_conteudo(None).build()
    recebido = []
    original = fake_ai_provider.gerar_conteudo_modulo

    def _espia(tema_titulo, modulo_titulo, modulo_descricao, conteudos_fontes, *args, **kwargs):
        recebido.append(conteudos_fontes)
        return original(
            tema_titulo, modulo_titulo, modulo_descricao, conteudos_fontes, *args, **kwargs
        )

    fake_ai_provider.gerar_conteudo_modulo = _espia

    gerar_conteudo_modulo(modulo, tema, InMemoryModuloRepository(), fake_ai_provider)

    assert recebido == [["Fontes consultadas: a.com, b.com\n\nMesmo texto."]]


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
