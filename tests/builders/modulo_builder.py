import uuid

from app.models.modulo import STATUS_PRONTO, Modulo


class ModuloBuilder:
    def __init__(self):
        self._id = uuid.uuid4()
        self._tema_id = uuid.uuid4()
        self._titulo = "Parte 1: Causas"
        self._descricao: str | None = None
        self._ordem = 0
        self._status = STATUS_PRONTO
        self._conteudo: str | None = "Conteúdo de teste do módulo."

    def com_id(self, modulo_id: uuid.UUID) -> "ModuloBuilder":
        self._id = modulo_id
        return self

    def com_tema_id(self, tema_id: uuid.UUID) -> "ModuloBuilder":
        self._tema_id = tema_id
        return self

    def com_titulo(self, titulo: str) -> "ModuloBuilder":
        self._titulo = titulo
        return self

    def com_ordem(self, ordem: int) -> "ModuloBuilder":
        self._ordem = ordem
        return self

    def com_status(self, status: str) -> "ModuloBuilder":
        self._status = status
        return self

    def pronto(self) -> "ModuloBuilder":
        self._status = STATUS_PRONTO
        return self

    def com_conteudo(self, conteudo: str | None) -> "ModuloBuilder":
        self._conteudo = conteudo
        return self

    def build(self) -> Modulo:
        return Modulo(
            id=self._id,
            tema_id=self._tema_id,
            titulo=self._titulo,
            descricao=self._descricao,
            ordem=self._ordem,
            status=self._status,
            conteudo=self._conteudo,
        )
