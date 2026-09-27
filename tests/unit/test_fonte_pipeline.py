import logging
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.ai.grounding import fontes_a_partir_do_grounding
from app.models.fonte import TIPO_BUSCA_AUTOMATICA, Fonte
from app.services.fonte_pipeline import (
    buscar_fontes_tema,
    conteudos_para_geracao,
    nomes_das_fontes,
)
from tests.builders.tema_builder import TemaBuilder


def _fonte(conteudo="texto", origem=None, metadata=None) -> Fonte:
    return Fonte(
        id=uuid.uuid4(),
        tema_id=uuid.uuid4(),
        tipo=TIPO_BUSCA_AUTOMATICA,
        origem=origem,
        conteudo_extraido=conteudo,
        metadata_=metadata,
    )


def _chunk(titulo, uri="https://redirect.example/x"):
    return SimpleNamespace(web=SimpleNamespace(title=titulo, uri=uri))


# --- grounding -> FonteEncontrada ---


def test_grounding_devolve_uma_fonte_com_o_texto_uma_unica_vez():
    fontes = fontes_a_partir_do_grounding(
        "texto", [_chunk("a.com"), _chunk("b.com"), _chunk("c.com")], "Tema"
    )

    assert len(fontes) == 1
    assert fontes[0].conteudo == "texto"
    assert [r.titulo for r in fontes[0].referencias] == ["a.com", "b.com", "c.com"]


def test_grounding_sem_titulo_usa_o_dominio_e_depois_um_rotulo_generico():
    chunk_dominio = SimpleNamespace(web=SimpleNamespace(title=None, domain="d.com", uri=None))
    chunk_vazio = SimpleNamespace(web=SimpleNamespace(title=None, domain=None, uri=None))

    (fonte,) = fontes_a_partir_do_grounding("texto", [chunk_dominio, chunk_vazio], "Tema")

    assert [r.titulo for r in fonte.referencias] == ["d.com", "Fonte sobre Tema"]


def test_grounding_sem_chunks_registra_aviso(caplog):
    with caplog.at_level(logging.WARNING, logger="app.ai.grounding"):
        (fonte,) = fontes_a_partir_do_grounding("texto", [], "Tema")

    assert fonte.referencias == ()
    assert fonte.conteudo == "texto"
    assert "sem grounding_chunks" in caplog.text


# --- nomes das fontes (o que o aluno vê) ---


def test_nomes_das_fontes_le_as_referencias_sem_repetir():
    fonte = _fonte(
        metadata={
            "titulo": "Busca automática: Tema",
            "referencias": [
                {"titulo": "ufpel.edu.br", "origem": "https://redirect/1"},
                {"titulo": "descomplica.com.br", "origem": "https://redirect/2"},
                {"titulo": "ufpel.edu.br", "origem": "https://redirect/3"},
            ],
        }
    )

    assert nomes_das_fontes([fonte]) == ["ufpel.edu.br", "descomplica.com.br"]


def test_nomes_das_fontes_nunca_expoe_o_link_de_redirecionamento():
    fonte = _fonte(
        metadata={"referencias": [{"titulo": "a.com", "origem": "https://vertexaisearch/x"}]}
    )

    assert not any("http" in nome for nome in nomes_das_fontes([fonte]))


def test_nomes_das_fontes_aceita_linhas_antigas_uma_por_pagina():
    antigas = [
        _fonte(origem="https://redirect/1", metadata={"titulo": "querobolsa.com.br"}),
        _fonte(origem="https://redirect/2", metadata={"titulo": "ufpel.edu.br"}),
    ]

    assert nomes_das_fontes(antigas) == ["querobolsa.com.br", "ufpel.edu.br"]


def test_nomes_das_fontes_ignora_a_linha_de_fallback_sem_fonte_citada():
    antiga = _fonte(origem=None, metadata={"titulo": "Busca automática: Tema"})
    nova = _fonte(metadata={"titulo": "Busca automática: Tema", "referencias": []})

    assert nomes_das_fontes([antiga, nova]) == []


def test_nomes_das_fontes_sem_metadata():
    assert nomes_das_fontes([_fonte(metadata=None)]) == []


# --- textos enviados à geração de conteúdo ---


def test_conteudos_para_geracao_junta_textos_repetidos_e_cita_os_nomes():
    texto = "Feudalismo é..."
    fontes = [
        _fonte(texto, "https://r/1", {"titulo": "a.com"}),
        _fonte(texto, "https://r/2", {"titulo": "b.com"}),
    ]

    assert conteudos_para_geracao(fontes) == [f"Fontes consultadas: a.com, b.com\n\n{texto}"]


def test_conteudos_para_geracao_sem_nomes_devolve_o_texto_puro():
    assert conteudos_para_geracao([_fonte("só o texto", metadata=None)]) == ["só o texto"]


def test_conteudos_para_geracao_mantem_textos_diferentes_separados():
    fontes = [_fonte("um"), _fonte("dois")]

    assert conteudos_para_geracao(fontes) == ["um", "dois"]


# --- persistência ---


def test_buscar_fontes_tema_grava_as_referencias_no_metadata(fake_ai_provider):
    tema = TemaBuilder().build()
    tema_repo = MagicMock()

    buscar_fontes_tema(tema, tema_repo, fake_ai_provider)

    (chamada,) = tema_repo.adicionar_fonte.call_args_list
    fonte = chamada.args[0]
    assert fonte.conteudo_extraido == "Conteúdo de teste."
    assert fonte.metadata_["referencias"] == [
        {"titulo": "example.org", "origem": "https://redirect.example/1"}
    ]
    assert nomes_das_fontes([fonte]) == ["example.org"]
