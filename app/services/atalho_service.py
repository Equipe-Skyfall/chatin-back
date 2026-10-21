"""Answers a few common chat requests without the LLM.

`intencao_service` says which request a short message is (or that it is not
one of them); here each intent gets its answer straight from the same services
the app's own routes use, so the numbers match `/progresso`, `/recomendacao`,
`/xp/meu` and `/ranking`. Anything the classifier is unsure about is not
answered here at all - it goes to the agent as usual (`tentar_atalho` returns
`None`).
"""

from app.ai.schemas import FerramentaContexto
from app.repositories.perfil_repository import PerfilRepository
from app.services import dificuldade_service, intencao_service, xp_service
from app.services.agent_tools_aluno import executar_ferramenta_aluno

TAMANHO_DO_TOPO = 5
# How far down the ranking a student's own position is looked up.
LIMITE_DA_POSICAO = 100


def _desempenho(ctx: FerramentaContexto) -> str:
    texto = executar_ferramenta_aluno("meu_desempenho", {}, ctx)
    if texto.startswith("O aluno ainda não tem"):
        return "Você ainda não tem nenhum progresso registrado."
    # The tool's own legend is written for the model ("o aluno ..."); the student
    # gets the same cut-offs in a line of their own.
    linhas = [linha for linha in texto.splitlines() if not linha.startswith("Níveis por tema:")]
    if len(linhas) != len(texto.splitlines()):
        baixo, alto = dificuldade_service.LIMIAR_BAIXO, dificuldade_service.LIMIAR_ALTO
        linhas.append(
            f"Níveis por tema: baixo = menos de {baixo}% de acerto; médio = de {baixo}% a menos "
            f"de {alto}%; alto = {alto}% ou mais. "
            "Temas que não aparecem ainda não têm questões respondidas."
        )
    return "Aqui está o seu desempenho:\n" + "\n".join(linhas)


def _proximos_estudos(ctx: FerramentaContexto) -> str:
    lista = executar_ferramenta_aluno("proximos_estudos", {}, ctx)
    if lista.startswith("Não há"):
        return "No momento não há nenhum módulo liberado para você estudar."
    return (
        "Estes são os módulos que recomendo você estudar agora, do mais urgente ao menos:\n" + lista
    )


def _xp(ctx: FerramentaContexto) -> str:
    total = ctx.xp_repo.total_por_usuario(ctx.user_id)
    nivel = xp_service.calcular_nivel(total)
    if nivel.nivel == 0:
        situacao = f"Você tem {total} XP e ainda não chegou ao nível 1"
    else:
        situacao = f"Você tem {total} XP e está no nível {nivel.nivel}"
    return (
        f"{situacao}. Faltam {nivel.xp_faltando_proximo_nivel} XP para o nível {nivel.nivel + 1}."
    )


def _ranking(ctx: FerramentaContexto, perfil_repo: PerfilRepository) -> str:
    entradas = ctx.xp_repo.ranking_global(LIMITE_DA_POSICAO)
    if not entradas:
        return "Ainda ninguém tem XP no ranking."
    nomes = perfil_repo.nomes_por_ids([uid for uid, _ in entradas[:TAMANHO_DO_TOPO]])
    linhas = [
        f"{posicao}. {nomes.get(uid) or 'Aluno'} - {xp} XP"
        for posicao, (uid, xp) in enumerate(entradas[:TAMANHO_DO_TOPO], start=1)
    ]
    minha = next(
        (
            (posicao, xp)
            for posicao, (uid, xp) in enumerate(entradas, start=1)
            if uid == ctx.user_id
        ),
        None,
    )
    if minha is not None:
        linhas.append(f"Sua posição: {minha[0]}º, com {minha[1]} XP.")
    else:
        linhas.append(f"Você ainda não está entre os {LIMITE_DA_POSICAO} primeiros do ranking.")
    return "Ranking geral de XP:\n" + "\n".join(linhas)


def tentar_atalho(
    mensagem: str, ctx: FerramentaContexto, perfil_repo: PerfilRepository
) -> str | None:
    """The answer to a message that is clearly one of the known requests, or
    `None` when it should go to the agent."""
    classificacao = intencao_service.classificar_intencao(mensagem)
    if classificacao is None:
        return None
    if classificacao.intencao == intencao_service.INTENCAO_DESEMPENHO:
        return _desempenho(ctx)
    if classificacao.intencao == intencao_service.INTENCAO_PROXIMOS_ESTUDOS:
        return _proximos_estudos(ctx)
    if classificacao.intencao == intencao_service.INTENCAO_XP:
        return _xp(ctx)
    if classificacao.intencao == intencao_service.INTENCAO_RANKING:
        return _ranking(ctx, perfil_repo)
    return None
