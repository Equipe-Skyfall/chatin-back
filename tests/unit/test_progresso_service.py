import uuid

from app.models.progresso import STATUS_CONCLUIDO, STATUS_DISPONIVEL, ProgressoUsuario
from app.services import progresso_service
from tests.builders.materia_builder import MateriaBuilder
from tests.builders.modulo_builder import ModuloBuilder
from tests.builders.tema_builder import TemaBuilder


def _progresso(user_id, modulo_id, status):
    return ProgressoUsuario(
        id=uuid.uuid4(), user_id=user_id, modulo_id=modulo_id, status=status, tentativas_count=1
    )


def test_primeiro_modulo_disponivel_sem_progresso():
    tema_id = uuid.uuid4()
    modulo_1 = ModuloBuilder().com_tema_id(tema_id).com_ordem(0).pronto().build()
    modulo_2 = ModuloBuilder().com_tema_id(tema_id).com_ordem(1).pronto().build()

    estados = progresso_service._estados_modulos([modulo_1, modulo_2], {}, tema_liberado=True)

    assert dict((m.id, e) for m, e in estados)[modulo_1.id] == "disponivel"
    assert dict((m.id, e) for m, e in estados)[modulo_2.id] == "bloqueado"


def test_segundo_modulo_libera_quando_primeiro_concluido():
    user_id = uuid.uuid4()
    tema_id = uuid.uuid4()
    modulo_1 = ModuloBuilder().com_tema_id(tema_id).com_ordem(0).pronto().build()
    modulo_2 = ModuloBuilder().com_tema_id(tema_id).com_ordem(1).pronto().build()
    progresso_map = {modulo_1.id: _progresso(user_id, modulo_1.id, STATUS_CONCLUIDO)}

    estados = dict(
        (m.id, e)
        for m, e in progresso_service._estados_modulos(
            [modulo_1, modulo_2], progresso_map, tema_liberado=True
        )
    )

    assert estados[modulo_1.id] == "concluido"
    assert estados[modulo_2.id] == "disponivel"


def test_modulos_bloqueados_quando_tema_bloqueado():
    tema_id = uuid.uuid4()
    modulo_1 = ModuloBuilder().com_tema_id(tema_id).com_ordem(0).pronto().build()

    estados = progresso_service._estados_modulos([modulo_1], {}, tema_liberado=False)

    assert estados[0][1] == "bloqueado"


def test_montar_trilha_segundo_tema_bloqueado_ate_primeiro_completo():
    materia_id = uuid.uuid4()

    modulo_a = ModuloBuilder().com_ordem(0).pronto().build()
    tema_1 = (
        TemaBuilder()
        .com_materia_id(materia_id)
        .com_ordem(0)
        .pronto()
        .com_modulos([modulo_a])
        .build()
    )
    modulo_a.tema_id = tema_1.id

    modulo_b = ModuloBuilder().com_ordem(0).pronto().build()
    tema_2 = (
        TemaBuilder()
        .com_materia_id(materia_id)
        .com_ordem(1)
        .pronto()
        .com_modulos([modulo_b])
        .build()
    )
    modulo_b.tema_id = tema_2.id

    materia = MateriaBuilder().com_id(materia_id).com_temas([tema_1, tema_2]).build()

    trilha = progresso_service.montar_trilha([materia], [])

    temas_out = {t.id: t for t in trilha.materias[0].temas}
    assert temas_out[tema_1.id].estado == "disponivel"
    assert temas_out[tema_2.id].estado == "bloqueado"


def test_montar_trilha_segundo_tema_libera_quando_primeiro_concluido():
    user_id = uuid.uuid4()
    materia_id = uuid.uuid4()

    modulo_a = ModuloBuilder().com_ordem(0).pronto().build()
    tema_1 = (
        TemaBuilder()
        .com_materia_id(materia_id)
        .com_ordem(0)
        .pronto()
        .com_modulos([modulo_a])
        .build()
    )
    modulo_a.tema_id = tema_1.id

    modulo_b = ModuloBuilder().com_ordem(0).pronto().build()
    tema_2 = (
        TemaBuilder()
        .com_materia_id(materia_id)
        .com_ordem(1)
        .pronto()
        .com_modulos([modulo_b])
        .build()
    )
    modulo_b.tema_id = tema_2.id

    materia = MateriaBuilder().com_id(materia_id).com_temas([tema_1, tema_2]).build()
    progresso_rows = [_progresso(user_id, modulo_a.id, STATUS_CONCLUIDO)]

    trilha = progresso_service.montar_trilha([materia], progresso_rows)

    temas_out = {t.id: t for t in trilha.materias[0].temas}
    assert temas_out[tema_1.id].estado == "concluido"
    assert temas_out[tema_2.id].estado == "disponivel"


def test_atualizar_progresso_primeira_tentativa_cria_registro():
    from tests.fakes.in_memory_repositories import InMemoryProgressoRepository, InMemoryXpRepository

    repo = InMemoryProgressoRepository()
    xp_repo = InMemoryXpRepository()
    user_id, modulo_id, materia_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    progresso = progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 40.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )

    assert progresso.tentativas_count == 1
    assert float(progresso.melhor_pontuacao) == 40.0
    assert progresso.status == STATUS_DISPONIVEL
    assert xp_repo.total_por_usuario(user_id) == 20  # first attempt, failing tier


def test_atualizar_progresso_aprova_acima_do_limite():
    from tests.fakes.in_memory_repositories import InMemoryProgressoRepository, InMemoryXpRepository

    repo = InMemoryProgressoRepository()
    xp_repo = InMemoryXpRepository()
    user_id, modulo_id, materia_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    progresso = progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 80.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )

    assert progresso.status == STATUS_CONCLUIDO
    assert xp_repo.total_por_usuario(user_id) == 100  # first attempt, "bom" tier (80-99%)


def test_atualizar_progresso_melhor_pontuacao_nunca_diminui():
    from tests.fakes.in_memory_repositories import InMemoryProgressoRepository, InMemoryXpRepository

    repo = InMemoryProgressoRepository()
    xp_repo = InMemoryXpRepository()
    user_id, modulo_id, materia_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 80.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )
    progresso = progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 50.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )

    assert float(progresso.melhor_pontuacao) == 80.0
    assert progresso.tentativas_count == 2
    # the second (worse) attempt earns no additional XP - only the first one did
    assert xp_repo.total_por_usuario(user_id) == 100


def test_atualizar_progresso_retentativa_com_melhoria_ganha_xp():
    from tests.fakes.in_memory_repositories import InMemoryProgressoRepository, InMemoryXpRepository

    repo = InMemoryProgressoRepository()
    xp_repo = InMemoryXpRepository()
    user_id, modulo_id, materia_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 60.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )
    xp_apos_primeira = xp_repo.total_por_usuario(user_id)
    progresso_service.atualizar_progresso(
        repo, user_id, modulo_id, materia_id, 90.0, limite_aprovacao=60.0, xp_repo=xp_repo
    )

    # retake that beats the previous best earns the improvement as bonus XP
    assert xp_repo.total_por_usuario(user_id) == xp_apos_primeira + 30
