import re

from pydantic import BaseModel, field_validator

_APELIDO = re.compile(r"^[\w.\- ]{3,20}$")


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
        return valor


class ApelidoOut(BaseModel):
    apelido: str | None
