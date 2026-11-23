from pydantic import BaseModel


class UsuarioApagadoOut(BaseModel):
    user_id: str
    # Rows deleted per table (tables with nothing to delete are left out).
    apagados: dict[str, int]
    # Trilhas the user created: kept, since other students may be studying them.
    materias_proprias_mantidas: int
