import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import (
    ConteudoIndisponivelException,
    ConversaNaoEncontradaException,
    ResumoEstudoSemModuloException,
)
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.models.fonte import Fonte
from app.services import resumo_estudo_service
from tests.builders.materia_builder import MateriaBuilder
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder
from tests.fakes.in_memory_repositories import (
    InMemoryConversaRepository,
    InMemoryModuloRepository,
    InMemoryResumoEstudoRepository,
)


def _conversa(modulo_id=None, user_id: str = "user-1", n_mensagens: int = 2) -> Conversa:
    conversa = Conversa(id=uuid.uuid4(), user_id=user_id, tipo=TIPO_ALUNO, modulo_id=modulo_id)
    conversa.updated_at = datetime.now(UTC)
    conversa.mensagens = [
        Mensagem(
            conversa_id=conversa.id,
            papel=PAPEL_USUARIO if i % 2 == 0 else PAPEL_ASSISTENTE,
            conteudo=f"mensagem {i}",
            ordem=i,
        )
        for i in range(n_mensagens)
    ]
    return conversa


def _modulo(modulo_id: uuid.UUID, conteudo: str | None = "Conteúdo do módulo."):
    modulo = ModuloBuilder().com_id(modulo_id).com_conteudo(conteudo).build()
    tema = TemaBuilder().com_titulo("Cálculo 1").build()
    tema.materia = MateriaBuilder().com_nome("Matemática").build()
    modulo.tema = tema
    return modulo


def _repos(modulo):
    modulo_repo = InMemoryModuloRepository()
    modulo_repo.seed(modulo)
    return InMemoryConversaRepository(), modulo_repo, InMemoryResumoEstudoRepository()


def test_gera_e_persiste_resumo_uma_vez(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)

    resumo = resumo_estudo_service.gerar_resumo(
        "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )

    assert fake_ai_provider.gerar_resumo_estudo_calls == 1
    assert resumo.modulo_id == modulo_id
    assert resumo.conversa_id == conversa.id
    assert resumo.titulo == "Parte 1: Causas"
    assert resumo.materia_nome == "Matemática"
    assert resumo.tema_titulo == "Cálculo 1"
    assert resumo.conteudo["visao_geral"] == "Visão geral de Parte 1: Causas."
    assert resumo.conteudo["conceitos_chave"] == [
        {"termo": "Conceito", "explicacao": "Explicação de teste."}
    ]
    assert list(resumo_repo.resumos.values()) == [resumo]


def test_fontes_do_resumo_vem_das_fontes_reais_do_tema(fake_ai_provider):
    modulo_id = uuid.uuid4()
    modulo = _modulo(modulo_id)
    modulo.tema.fontes = [
        Fonte(
            tema_id=modulo.tema.id,
            conteudo_extraido="texto",
            metadata_={
                "titulo": "Busca automática: Cálculo 1",
                "referencias": [
                    {"titulo": "ufpel.edu.br", "origem": "https://redirect/1"},
                    {"titulo": "descomplica.com.br", "origem": "https://redirect/2"},
                ],
            },
        )
    ]
    conversa_repo, modulo_repo, resumo_repo = _repos(modulo)
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)

    resumo = resumo_estudo_service.gerar_resumo(
        "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )

    assert resumo.conteudo["fontes"] == ["ufpel.edu.br", "descomplica.com.br"]


def test_resumo_de_tema_sem_fontes_citadas_tem_lista_vazia(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)

    resumo = resumo_estudo_service.gerar_resumo(
        "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )

    assert resumo.conteudo["fontes"] == []


def test_regenerar_faz_upsert_sem_duplicar(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)

    primeiro = resumo_estudo_service.gerar_resumo(
        "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )
    segundo = resumo_estudo_service.gerar_resumo(
        "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )

    assert fake_ai_provider.gerar_resumo_estudo_calls == 2
    assert primeiro.id == segundo.id
    assert len(resumo_repo.resumos) == 1


def test_agrega_conversas_do_mesmo_modulo(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    primeira = _conversa(modulo_id=modulo_id, n_mensagens=1)
    segunda = _conversa(modulo_id=modulo_id, n_mensagens=1)
    conversa_repo.add(primeira)
    conversa_repo.add(segunda)

    resumo_estudo_service.gerar_resumo(
        "user-1", primeira.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
    )

    (recebido,) = fake_ai_provider.resumos_estudo_recebidos
    conteudos = [m.conteudo for m in recebido["historico"]]
    assert "mensagem 0" in conteudos
    assert len(recebido["historico"]) == 2


def test_conversa_sem_modulo_e_rejeitada(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(modulo_id=None)
    conversa_repo.add(conversa)

    with pytest.raises(ResumoEstudoSemModuloException):
        resumo_estudo_service.gerar_resumo(
            "user-1",
            conversa.id,
            conversa_repo,
            InMemoryModuloRepository(),
            InMemoryResumoEstudoRepository(),
            fake_ai_provider,
        )

    assert fake_ai_provider.gerar_resumo_estudo_calls == 0


def test_conversa_de_outro_usuario_e_rejeitada(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    conversa = _conversa(modulo_id=modulo_id, user_id="outro")
    conversa_repo.add(conversa)

    with pytest.raises(ConversaNaoEncontradaException):
        resumo_estudo_service.gerar_resumo(
            "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
        )


def test_modulo_sem_conteudo_e_rejeitado(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id, conteudo=None))
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)

    with pytest.raises(ConteudoIndisponivelException):
        resumo_estudo_service.gerar_resumo(
            "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
        )

    assert fake_ai_provider.gerar_resumo_estudo_calls == 0


def test_falha_de_ia_nao_persiste(fake_ai_provider):
    modulo_id = uuid.uuid4()
    conversa_repo, modulo_repo, resumo_repo = _repos(_modulo(modulo_id))
    conversa = _conversa(modulo_id=modulo_id)
    conversa_repo.add(conversa)
    fake_ai_provider.falhar_gerar_resumo_estudo = True

    with pytest.raises(RuntimeError):
        resumo_estudo_service.gerar_resumo(
            "user-1", conversa.id, conversa_repo, modulo_repo, resumo_repo, fake_ai_provider
        )

    assert resumo_repo.resumos == {}
