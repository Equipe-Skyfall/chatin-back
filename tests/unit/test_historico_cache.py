import uuid

from app.ai.schemas import MensagemAgente
from app.models.conversa import PAPEL_ASSISTENTE, PAPEL_USUARIO, Mensagem
from app.services import historico_cache
from tests.fakes.fake_redis import FakeRedisCliente
from tests.fakes.in_memory_repositories import InMemoryConversaRepository


def _mensagem(papel: str, conteudo: str, ordem: int) -> Mensagem:
    return Mensagem(conversa_id=uuid.uuid4(), papel=papel, conteudo=conteudo, ordem=ordem)


def test_redis_none_sempre_usa_postgres_e_nunca_toca_cache():
    conversa_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa_repo.seed(conversa_id, [_mensagem(PAPEL_USUARIO, "oi", 0)])

    historico = historico_cache.obter_historico_recente(conversa_id, conversa_repo, None, 20)

    assert [m.conteudo for m in historico] == ["oi"]

    # não deve levantar, mesmo sem cliente - é um no-op
    historico_cache.registrar_mensagem(
        conversa_id, MensagemAgente(papel=PAPEL_USUARIO, conteudo="oi"), None, 20
    )


def test_cache_hit_nao_consulta_postgres():
    conversa_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()  # vazio de propósito
    redis_cliente = FakeRedisCliente()
    historico_cache.registrar_mensagem(
        conversa_id, MensagemAgente(papel=PAPEL_USUARIO, conteudo="pergunta"), redis_cliente, 20
    )

    historico = historico_cache.obter_historico_recente(
        conversa_id, conversa_repo, redis_cliente, 20
    )

    assert [m.conteudo for m in historico] == ["pergunta"]


def test_cache_miss_cai_pro_postgres_e_repopula():
    conversa_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa_repo.seed(
        conversa_id,
        [_mensagem(PAPEL_USUARIO, "pergunta", 0), _mensagem(PAPEL_ASSISTENTE, "resposta", 1)],
    )
    redis_cliente = FakeRedisCliente()  # cache vazio

    historico = historico_cache.obter_historico_recente(
        conversa_id, conversa_repo, redis_cliente, 20
    )
    assert [m.conteudo for m in historico] == ["pergunta", "resposta"]

    # repopulado - uma segunda leitura já vem do cache, sem tocar o repo
    conversa_repo._conversas.clear()
    historico_repetido = historico_cache.obter_historico_recente(
        conversa_id, conversa_repo, redis_cliente, 20
    )
    assert [m.conteudo for m in historico_repetido] == ["pergunta", "resposta"]


def test_redis_indisponivel_na_leitura_cai_pro_postgres_sem_lancar():
    conversa_id = uuid.uuid4()
    conversa_repo = InMemoryConversaRepository()
    conversa_repo.seed(conversa_id, [_mensagem(PAPEL_USUARIO, "oi", 0)])
    redis_cliente = FakeRedisCliente(indisponivel=True)

    historico = historico_cache.obter_historico_recente(
        conversa_id, conversa_repo, redis_cliente, 20
    )

    assert [m.conteudo for m in historico] == ["oi"]


def test_redis_indisponivel_ao_registrar_nao_lanca():
    conversa_id = uuid.uuid4()
    redis_cliente = FakeRedisCliente(indisponivel=True)

    historico_cache.registrar_mensagem(
        conversa_id, MensagemAgente(papel=PAPEL_USUARIO, conteudo="oi"), redis_cliente, 20
    )  # não deve levantar


def test_janela_mantem_so_as_ultimas_n_mensagens():
    conversa_id = uuid.uuid4()
    redis_cliente = FakeRedisCliente()

    for i in range(5):
        historico_cache.registrar_mensagem(
            conversa_id, MensagemAgente(papel=PAPEL_USUARIO, conteudo=f"msg{i}"), redis_cliente, 3
        )

    historico = historico_cache.obter_historico_recente(
        conversa_id, InMemoryConversaRepository(), redis_cliente, 3
    )
    assert [m.conteudo for m in historico] == ["msg2", "msg3", "msg4"]


def test_lock_sem_redis_sempre_adquire():
    assert historico_cache.adquirir_lock(uuid.uuid4(), None) is True
    historico_cache.liberar_lock(uuid.uuid4(), None)  # não deve levantar


def test_lock_redis_indisponivel_adquire_mesmo_assim():
    redis_cliente = FakeRedisCliente(indisponivel=True)
    assert historico_cache.adquirir_lock(uuid.uuid4(), redis_cliente) is True
    historico_cache.liberar_lock(uuid.uuid4(), redis_cliente)  # não deve levantar


def test_lock_segunda_aquisicao_falha_ate_liberar():
    conversa_id = uuid.uuid4()
    redis_cliente = FakeRedisCliente()

    assert historico_cache.adquirir_lock(conversa_id, redis_cliente) is True
    assert historico_cache.adquirir_lock(conversa_id, redis_cliente) is False

    historico_cache.liberar_lock(conversa_id, redis_cliente)
    assert historico_cache.adquirir_lock(conversa_id, redis_cliente) is True


def test_lock_e_por_conversa():
    redis_cliente = FakeRedisCliente()
    conversa_a, conversa_b = uuid.uuid4(), uuid.uuid4()

    assert historico_cache.adquirir_lock(conversa_a, redis_cliente) is True
    assert historico_cache.adquirir_lock(conversa_b, redis_cliente) is True
