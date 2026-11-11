"""Builds the ranking payload: only apelidos leave the service, never the real
name or the user id (CH-100)."""

from app.schemas.xp import RankingEntradaOut, RankingOut

PREFIXO_SEM_APELIDO = "Aluno"


def apelido_de_exibicao(user_id: str, apelido: str | None) -> str:
    """The student's apelido, or a stable neutral name ("Aluno K3F9", from the
    tail of their id) while they have not chosen one."""
    if apelido:
        return apelido
    return f"{PREFIXO_SEM_APELIDO} {user_id[-4:].upper()}"


def montar_ranking(
    entradas: list[tuple[str, int]],
    apelidos: dict[str, str],
    user_id: str,
    minha_posicao: tuple[int, int] | None,
) -> RankingOut:
    """`entradas` is the top N as (user_id, xp) in order; `apelidos` maps the
    user ids of `entradas` and of `user_id`; `minha_posicao` is the caller's
    (position, xp) from the repository."""
    linhas = [
        RankingEntradaOut(
            posicao=i + 1,
            apelido=apelido_de_exibicao(uid, apelidos.get(uid)),
            xp=xp,
            eu=uid == user_id,
        )
        for i, (uid, xp) in enumerate(entradas)
    ]
    minha = None
    if minha_posicao is not None:
        posicao, xp = minha_posicao
        minha = RankingEntradaOut(
            posicao=posicao,
            apelido=apelido_de_exibicao(user_id, apelidos.get(user_id)),
            xp=xp,
            eu=True,
        )
    return RankingOut(entradas=linhas, minha_posicao=minha)
