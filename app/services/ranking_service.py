"""The name the ranking shows for a student: only the apelido, never the real
name or the user id (CH-100)."""

PREFIXO_SEM_APELIDO = "Aluno"


def apelido_de_exibicao(user_id: str, apelido: str | None) -> str:
    """The student's apelido, or a stable neutral name ("Aluno K3F9", from the
    tail of their id) while they have not chosen one."""
    if apelido:
        return apelido
    return f"{PREFIXO_SEM_APELIDO} {user_id[-4:].upper()}"
