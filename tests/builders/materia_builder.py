import uuid

from app.models.materia import Materia


class MateriaBuilder:
    def __init__(self):
        self._id = uuid.uuid4()
        self._nome = "Matéria de teste"
        self._temas: list = []

    def com_id(self, materia_id: uuid.UUID) -> "MateriaBuilder":
        self._id = materia_id
        return self

    def com_nome(self, nome: str) -> "MateriaBuilder":
        self._nome = nome
        return self

    def com_temas(self, temas: list) -> "MateriaBuilder":
        self._temas = temas
        return self

    def build(self) -> Materia:
        materia = Materia(id=self._id, nome=self._nome, descricao=None)
        materia.temas = self._temas
        return materia
