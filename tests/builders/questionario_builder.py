import uuid

from app.models.questao import Questao
from app.models.questionario import Questionario


class QuestionarioBuilder:
    """Builds a pool (`Questionario` + its `Questao`s) plus the gabarito map
    that would live in the `gabaritos` table - as a plain dict here, since
    tests exercise `grading_service` against fakes, not the real table.
    """

    def __init__(self):
        self._id = uuid.uuid4()
        self._modulo_id = uuid.uuid4()
        self._num_questoes = 12
        self._resposta_correta_padrao = "A"

    def com_id(self, questionario_id: uuid.UUID) -> "QuestionarioBuilder":
        self._id = questionario_id
        return self

    def com_modulo_id(self, modulo_id: uuid.UUID) -> "QuestionarioBuilder":
        self._modulo_id = modulo_id
        return self

    def com_num_questoes(self, n: int) -> "QuestionarioBuilder":
        self._num_questoes = n
        return self

    def com_resposta_correta_padrao(self, letra: str) -> "QuestionarioBuilder":
        self._resposta_correta_padrao = letra
        return self

    def build(self) -> tuple[Questionario, list[Questao], dict[uuid.UUID, str]]:
        questionario = Questionario(
            id=self._id,
            modulo_id=self._modulo_id,
            modelo_ia="fake-model",
        )
        questoes: list[Questao] = []
        gabarito_map: dict[uuid.UUID, str] = {}

        for i in range(self._num_questoes):
            questao_id = uuid.uuid4()
            questao = Questao(
                id=questao_id,
                questionario_id=self._id,
                ordem=i,
                enunciado=f"Questão de teste {i}",
                alternativas=[
                    {"letra": letra, "texto": f"Alternativa {letra}"} for letra in "ABCDE"
                ],
                explicacao=f"Explicação da questão {i}",
            )
            questoes.append(questao)
            gabarito_map[questao_id] = self._resposta_correta_padrao

        return questionario, questoes, gabarito_map
