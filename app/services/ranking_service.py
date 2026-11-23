"""The name the ranking shows for a student: the apelido they chose, else their
username (the one from the registration), else a neutral name - never the user
id (CH-100)."""

PREFIXO_SEM_APELIDO = "Aluno"


def apelido_de_exibicao(user_id: str, apelido: str | None, username: str | None = None) -> str:
    """The student's apelido; without one, their username (`perfis_usuario.nome`);
    without that either, a stable neutral name ("Aluno K3F9", from the tail of
    their id)."""
    if apelido:
        return apelido
    if username:
        return username
    return f"{PREFIXO_SEM_APELIDO} {user_id[-4:].upper()}"
