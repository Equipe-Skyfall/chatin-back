from app.services.curriculo_service import _conteudo_ja_coberto
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder


def test_sem_modulos_anteriores_retorna_vazio():
    tema = TemaBuilder().com_modulos([]).build()

    assert _conteudo_ja_coberto(tema, ordem_atual=0) == []


def test_retorna_conteudo_dos_modulos_com_ordem_menor_em_ordem():
    m0 = ModuloBuilder().com_ordem(0).com_conteudo("conteudo do modulo 0").build()
    m1 = ModuloBuilder().com_ordem(1).com_conteudo("conteudo do modulo 1").build()
    m2 = ModuloBuilder().com_ordem(2).com_conteudo("conteudo do modulo 2").build()
    tema = TemaBuilder().com_modulos([m2, m0, m1]).build()  # deliberately out of order

    assert _conteudo_ja_coberto(tema, ordem_atual=2) == [
        "conteudo do modulo 0",
        "conteudo do modulo 1",
    ]


def test_ignora_modulos_sem_conteudo_ainda():
    m0 = ModuloBuilder().com_ordem(0).com_conteudo(None).build()
    m1 = ModuloBuilder().com_ordem(1).com_conteudo("conteudo do modulo 1").build()
    tema = TemaBuilder().com_modulos([m0, m1]).build()

    assert _conteudo_ja_coberto(tema, ordem_atual=2) == ["conteudo do modulo 1"]


def test_nao_inclui_modulos_com_ordem_igual_ou_maior():
    m0 = ModuloBuilder().com_ordem(0).com_conteudo("conteudo do modulo 0").build()
    m1 = ModuloBuilder().com_ordem(1).com_conteudo("conteudo do modulo 1").build()
    tema = TemaBuilder().com_modulos([m0, m1]).build()

    assert _conteudo_ja_coberto(tema, ordem_atual=1) == ["conteudo do modulo 0"]


def test_exclui_modulo_id_informado_mesmo_com_ordem_menor():
    """Used by `regenerar_modulo` - the módulo being regenerated shouldn't
    cite its own (about-to-be-replaced) content as 'already covered'."""
    m0 = ModuloBuilder().com_ordem(0).com_conteudo("conteudo do modulo 0").build()
    tema = TemaBuilder().com_modulos([m0]).build()

    assert _conteudo_ja_coberto(tema, ordem_atual=0, excluir_modulo_id=m0.id) == []
