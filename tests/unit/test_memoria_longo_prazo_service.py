import uuid
from datetime import UTC, datetime, timedelta

from app.models.conversa import PAPEL_USUARIO, TIPO_ALUNO, Conversa, Mensagem
from app.services import memoria_longo_prazo_service
from tests.fakes.in_memory_repositories import InMemoryConversaRepository


def _conversa(
    conversa_id=None,
    user_id="user-1",
    modulo_id=None,
    mensagens=None,
    memoria_chave=None,
    memoria_embedding=None,
    memoria_gerada_em=None,
    updated_at=None,
) -> Conversa:
    conversa_id = conversa_id or uuid.uuid4()
    conversa = Conversa(
        id=conversa_id,
        user_id=user_id,
        tipo=TIPO_ALUNO,
        modulo_id=modulo_id or uuid.uuid4(),
    )
    conversa.mensagens = mensagens or []
    conversa.memoria_chave = memoria_chave
    conversa.memoria_embedding = memoria_embedding
    conversa.memoria_gerada_em = memoria_gerada_em
    conversa.updated_at = updated_at or datetime.now(UTC)
    return conversa


def _mensagem(conversa_id, papel, conteudo) -> Mensagem:
    return Mensagem(conversa_id=conversa_id, papel=papel, conteudo=conteudo, ordem=0)


def test_gera_memoria_quando_ausente(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(
        mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "não entendi limite lateral")]
    )
    conversa_repo.add(conversa)

    memoria_longo_prazo_service.obter_ou_gerar_memoria(conversa, conversa_repo, fake_ai_provider)

    assert fake_ai_provider.extrair_memoria_conversa_calls == 1
    assert fake_ai_provider.gerar_embedding_calls == 1
    assert conversa.memoria_chave is not None
    assert conversa.memoria_embedding is not None
    assert conversa.memoria_gerada_em is not None


def test_nao_gera_de_novo_quando_ja_atualizada(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    agora = datetime.now(UTC)
    conversa = _conversa(
        mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "oi")],
        memoria_chave="já tem memória",
        memoria_embedding=[0.1, 0.2],
        memoria_gerada_em=agora,
        updated_at=agora - timedelta(minutes=5),
    )
    conversa_repo.add(conversa)

    memoria_longo_prazo_service.obter_ou_gerar_memoria(conversa, conversa_repo, fake_ai_provider)

    assert fake_ai_provider.extrair_memoria_conversa_calls == 0
    assert fake_ai_provider.gerar_embedding_calls == 0
    assert conversa.memoria_chave == "já tem memória"


def test_regenera_quando_desatualizada(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    agora = datetime.now(UTC)
    conversa = _conversa(
        mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "nova dúvida")],
        memoria_chave="memória antiga",
        memoria_embedding=[0.1, 0.2],
        memoria_gerada_em=agora - timedelta(hours=1),
        updated_at=agora,  # conversa mudou depois da última memória
    )
    conversa_repo.add(conversa)

    memoria_longo_prazo_service.obter_ou_gerar_memoria(conversa, conversa_repo, fake_ai_provider)

    assert fake_ai_provider.extrair_memoria_conversa_calls == 1


def test_sem_mensagens_nao_chama_ia(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(mensagens=[])
    conversa_repo.add(conversa)

    memoria_longo_prazo_service.obter_ou_gerar_memoria(conversa, conversa_repo, fake_ai_provider)

    assert fake_ai_provider.extrair_memoria_conversa_calls == 0
    assert conversa.memoria_chave is None


def test_nada_relevante_nao_gera_embedding(fake_ai_provider):
    fake_ai_provider.memoria_extraida_fixa = "Nada relevante a registrar."
    conversa_repo = InMemoryConversaRepository()
    conversa = _conversa(mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "oi")])
    conversa_repo.add(conversa)

    memoria_longo_prazo_service.obter_ou_gerar_memoria(conversa, conversa_repo, fake_ai_provider)

    assert fake_ai_provider.extrair_memoria_conversa_calls == 1
    assert fake_ai_provider.gerar_embedding_calls == 0
    assert conversa.memoria_chave == "Nada relevante a registrar."
    assert conversa.memoria_embedding is None


def test_atualizar_memorias_do_modulo_so_toca_outras_conversas_do_mesmo_modulo(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    modulo_id = uuid.uuid4()
    atual = _conversa(modulo_id=modulo_id, mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "x")])
    outra_mesmo_modulo = _conversa(
        modulo_id=modulo_id, mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "y")]
    )
    outro_modulo = _conversa(mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "z")])
    outro_usuario = _conversa(
        user_id="user-2",
        modulo_id=modulo_id,
        mensagens=[_mensagem(uuid.uuid4(), PAPEL_USUARIO, "w")],
    )
    for c in (atual, outra_mesmo_modulo, outro_modulo, outro_usuario):
        conversa_repo.add(c)

    memoria_longo_prazo_service.atualizar_memorias_do_modulo(
        "user-1", modulo_id, atual.id, conversa_repo, fake_ai_provider
    )

    assert fake_ai_provider.extrair_memoria_conversa_calls == 1
    assert outra_mesmo_modulo.memoria_chave is not None
    assert atual.memoria_chave is None
    assert outro_modulo.memoria_chave is None
    assert outro_usuario.memoria_chave is None


def test_buscar_memorias_similares_rankeia_pela_mais_proxima(fake_ai_provider):
    conversa_repo = InMemoryConversaRepository()
    modulo_id = uuid.uuid4()
    excluir_id = uuid.uuid4()

    proxima = _conversa(
        modulo_id=modulo_id,
        memoria_chave="fala de limites",
        memoria_embedding=[1.0, 0.0],
        memoria_gerada_em=datetime.now(UTC),
    )
    distante = _conversa(
        modulo_id=modulo_id,
        memoria_chave="fala de história",
        memoria_embedding=[0.0, 1.0],
        memoria_gerada_em=datetime.now(UTC),
    )
    conversa_repo.add(proxima)
    conversa_repo.add(distante)

    resultado = conversa_repo.buscar_memorias_similares(
        "user-1", modulo_id, [1.0, 0.0], 1, excluir_id
    )

    assert resultado == ["fala de limites"]
