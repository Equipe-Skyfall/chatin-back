import uuid

from app.models.tema import STATUS_PRONTO, Tema


class TemaBuilder:
    """Fluent constructor for a `Tema` ORM instance with sensible defaults, so
    tests only specify what they care about (e.g. `TemaBuilder().pronto().build()`).
    """

    def __init__(self):
        self._id = uuid.uuid4()
        self._materia_id = uuid.uuid4()
        self._titulo = "Revolução Francesa"
        self._descricao: str | None = None
        self._ordem = 0
        self._status = STATUS_PRONTO
        self._modulos: list = []
        self._direcionamento: str | None = None
        self._fontes: list = []

    def com_id(self, tema_id: uuid.UUID) -> "TemaBuilder":
        self._id = tema_id
        return self

    def com_materia_id(self, materia_id: uuid.UUID) -> "TemaBuilder":
        self._materia_id = materia_id
        return self

    def com_titulo(self, titulo: str) -> "TemaBuilder":
        self._titulo = titulo
        return self

    def com_ordem(self, ordem: int) -> "TemaBuilder":
        self._ordem = ordem
        return self

    def com_status(self, status: str) -> "TemaBuilder":
        self._status = status
        return self

    def pronto(self) -> "TemaBuilder":
        self._status = STATUS_PRONTO
        return self

    def com_modulos(self, modulos: list) -> "TemaBuilder":
        self._modulos = modulos
        return self

    def com_direcionamento(self, direcionamento: str | None) -> "TemaBuilder":
        self._direcionamento = direcionamento
        return self

    def com_fontes(self, fontes: list) -> "TemaBuilder":
        self._fontes = fontes
        return self

    def build(self) -> Tema:
        tema = Tema(
            id=self._id,
            materia_id=self._materia_id,
            titulo=self._titulo,
            descricao=self._descricao,
            ordem=self._ordem,
            status=self._status,
            direcionamento=self._direcionamento,
        )
        tema.modulos = self._modulos
        tema.fontes = self._fontes
        return tema
