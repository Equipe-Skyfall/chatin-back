"""In-memory stand-ins for the repository interfaces, backed by plain Python
dicts/lists instead of a database. Used by service-layer unit tests
(`grading_service`, `progresso_service`) so they run with no DB at all.
"""

import uuid

from app.models.progresso import STATUS_DISPONIVEL, ProgressoUsuario
from app.models.questao import Questao
from app.models.questionario import Questionario
from app.models.tentativa import RespostaTentativa, Tentativa, TentativaQuestao


class _FakeSession:
    """Stand-in for the `.db` a real repository exposes - pipelines call
    `repo.db.rollback()` on failure; the fakes need that attribute to exist."""

    def rollback(self) -> None:
        pass


class InMemoryModuloRepository:
    def __init__(self):
        self.db = _FakeSession()
        self.statuses: dict[uuid.UUID, str] = {}

    def atualizar_status(self, modulo, status: str) -> None:
        modulo.status = status
        self.statuses[modulo.id] = status

    def definir_conteudo(self, modulo, conteudo: str, modelo_ia: str) -> None:
        modulo.conteudo = conteudo
        modulo.conteudo_modelo_ia = modelo_ia

    def atualizar_conteudo(self, modulo, conteudo: str) -> None:
        modulo.conteudo = conteudo

    def commit(self) -> None:
        pass


class InMemoryQuestionarioRepository:
    def __init__(self):
        self.db = _FakeSession()
        self.questoes: dict[uuid.UUID, Questao] = {}
        self.gabaritos: dict[uuid.UUID, str] = {}
        self._questionarios_by_modulo: dict[uuid.UUID, Questionario] = {}
        self._pool_por_tema: dict[uuid.UUID, list[uuid.UUID]] = {}

    def seed_pool_tema(self, tema_id: uuid.UUID, questao_ids: list[uuid.UUID]) -> None:
        """Test double shortcut: register a tema's review-quiz pool directly,
        rather than modeling the full módulo/tema join the real repository
        query does."""
        self._pool_por_tema[tema_id] = list(questao_ids)

    def get_questao_ids_pool_por_tema(self, tema_id: uuid.UUID) -> list[uuid.UUID]:
        return list(self._pool_por_tema.get(tema_id, []))

    def seed(
        self,
        questionario: Questionario,
        questoes: list[Questao],
        gabarito_map: dict[uuid.UUID, str],
    ) -> None:
        self._questionarios_by_modulo[questionario.modulo_id] = questionario
        for questao in questoes:
            self.questoes[questao.id] = questao
        self.gabaritos.update(gabarito_map)

    def get_by_modulo(self, modulo_id: uuid.UUID) -> Questionario | None:
        return self._questionarios_by_modulo.get(modulo_id)

    def get_questao_ids_pool(self, questionario_id: uuid.UUID) -> list[uuid.UUID]:
        return [q.id for q in self.questoes.values() if q.questionario_id == questionario_id]

    def get_questoes_by_ids(self, questao_ids: list[uuid.UUID]) -> list[Questao]:
        return [self.questoes[qid] for qid in questao_ids if qid in self.questoes]

    def get_gabarito_map(self, questao_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        return {qid: self.gabaritos[qid] for qid in questao_ids if qid in self.gabaritos}

    def estatisticas_por_questao(
        self, questao_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, float]]:
        """Test double: no answer history is seeded here, so every question
        looks brand-new (0 respostas) - callers fall back to the cold-start
        default difficulty, matching real behavior for an unanswered question."""
        return dict.fromkeys(questao_ids, (0, 0.0))

    def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = uuid.uuid4()
        self._questionarios_by_modulo[entity.modulo_id] = entity
        return entity

    def add_questao(self, questao: Questao) -> Questao:
        if questao.id is None:
            questao.id = uuid.uuid4()
        self.questoes[questao.id] = questao
        return questao

    def add_gabarito(self, gabarito) -> None:
        self.gabaritos[gabarito.questao_id] = gabarito.resposta_correta

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass


class InMemoryTentativaRepository:
    def __init__(self):
        self.tentativas: dict[uuid.UUID, Tentativa] = {}
        self._questoes_por_tentativa: dict[uuid.UUID, set[uuid.UUID]] = {}
        self.respostas: list[RespostaTentativa] = []

    def add(self, tentativa: Tentativa) -> Tentativa:
        if tentativa.id is None:
            tentativa.id = uuid.uuid4()
        self.tentativas[tentativa.id] = tentativa
        return tentativa

    def get(self, tentativa_id: uuid.UUID) -> Tentativa | None:
        return self.tentativas.get(tentativa_id)

    def add_tentativa_questoes(self, itens: list[TentativaQuestao]) -> None:
        for item in itens:
            self._questoes_por_tentativa.setdefault(item.tentativa_id, set()).add(item.questao_id)

    def get_tentativa_questao_ids(self, tentativa_id: uuid.UUID) -> set[uuid.UUID]:
        return set(self._questoes_por_tentativa.get(tentativa_id, set()))

    def add_respostas(self, respostas: list[RespostaTentativa]) -> None:
        self.respostas.extend(respostas)

    def marcar_concluida(self, tentativa: Tentativa, pontuacao: float, total_corretas: int) -> None:
        tentativa.status = "concluida"
        tentativa.pontuacao = pontuacao
        tentativa.total_corretas = total_corretas

    def media_pontuacao_concluidas(self, user_id: str) -> float | None:
        pontuacoes = [
            float(t.pontuacao)
            for t in self.tentativas.values()
            if t.user_id == user_id and t.status == "concluida" and t.pontuacao is not None
        ]
        return sum(pontuacoes) / len(pontuacoes) if pontuacoes else None

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def refresh(self, entity) -> None:
        pass


class InMemoryProgressoRepository:
    def __init__(self):
        self.rows: dict[tuple[str, uuid.UUID], ProgressoUsuario] = {}

    def get_by_user_and_modulo(self, user_id: str, modulo_id: uuid.UUID) -> ProgressoUsuario | None:
        return self.rows.get((user_id, modulo_id))

    def list_by_user_and_modulos(
        self, user_id: str, modulo_ids: list[uuid.UUID]
    ) -> list[ProgressoUsuario]:
        return [
            row for (uid, mid), row in self.rows.items() if uid == user_id and mid in modulo_ids
        ]

    def list_by_user(self, user_id: str) -> list[ProgressoUsuario]:
        return [row for (uid, _), row in self.rows.items() if uid == user_id]

    def get_or_create(self, user_id: str, modulo_id: uuid.UUID) -> ProgressoUsuario:
        key = (user_id, modulo_id)
        if key not in self.rows:
            self.rows[key] = ProgressoUsuario(
                id=uuid.uuid4(),
                user_id=user_id,
                modulo_id=modulo_id,
                status=STATUS_DISPONIVEL,
                tentativas_count=0,
            )
        return self.rows[key]

    def add(self, entity: ProgressoUsuario) -> ProgressoUsuario:
        self.rows[(entity.user_id, entity.modulo_id)] = entity
        return entity

    def commit(self) -> None:
        pass


class InMemoryXpRepository:
    def __init__(self):
        self.eventos: list = []

    def add(self, entity) -> None:
        self.eventos.append(entity)
        return entity

    def commit(self) -> None:
        pass

    def total_por_usuario(self, user_id: str) -> int:
        return sum(e.quantidade for e in self.eventos if e.user_id == user_id)

    def total_por_usuario_e_materia(self, user_id: str, materia_id: uuid.UUID) -> int:
        return sum(
            e.quantidade
            for e in self.eventos
            if e.user_id == user_id and e.materia_id == materia_id
        )
