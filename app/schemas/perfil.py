import re

from pydantic import BaseModel, field_validator

_APELIDO = re.compile(r"^[\w.\- ]{3,20}$")
# Same shape as the neutral name the ranking shows while no apelido is chosen
# ("Aluno K3F9"); reserved so nobody can pass as someone else's fallback.
_RESERVADO = re.compile(r"^aluno [0-9a-z]{4}$", re.IGNORECASE)


class ApelidoIn(BaseModel):
    apelido: str

    @field_validator("apelido")
    @classmethod
    def validar(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not _APELIDO.fullmatch(valor):
            raise ValueError(
                "O apelido deve ter de 3 a 20 caracteres: letras, números, espaço, ponto, "
                "hífen ou sublinhado."
            )
        if _RESERVADO.fullmatch(valor):
            raise ValueError("Esse formato de apelido é reservado. Escolha outro.")
        return valor


class ApelidoOut(BaseModel):
    apelido: str | None
