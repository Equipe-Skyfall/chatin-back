"""The student agent's tool registry - deliberately tiny compared to the
admin's 21 tools (`agent_tools.py`): a student can search across the public
curriculum (official + every student's trilha), see their own performance,
and create their own trilha when nothing fits. Never destructive (no
delete), never sees another student's private data (there isn't any -
trilhas are public by design, but XP/progresso queries here are always
scoped to `ctx.user_id`). Shares `FerramentaContexto` and the
error-handling shape of `agent_tools.executar_ferramenta`, but is a
separate dispatch table - the two audiences' tools are never mixed.
"""

from collections.abc import Callable
from typing import Any

from app.ai.schemas import FerramentaContexto, FerramentaDeclaracao
from app.core.exceptions import AppException
from app.services import curriculo_service, trilha_pessoal_service

# Mirrors `progresso_service`'s default (see `Settings.PONTUACAO_MINIMA_
# APROVACAO`) - not threaded through `FerramentaContexto` since this is the
# only tool that needs it; a real per-request value would be a small
# addition if that ever changes.
_PONTUACAO_STRUGGLING = 60.0


def _buscar_conteudo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    termo = (args.get("termo") or "").strip().lower()
    if not termo:
        return "Informe um termo de busca (ex.: 'cálculo', 'funções quadráticas')."

    materias = [
        m
        for m in ctx.materia_repo.list_publica()
        if termo in m.nome.lower() or (m.descricao and termo in m.descricao.lower())
    ]
    if not materias:
        return (
            f"Nenhum conteúdo encontrado sobre '{termo}'. Você pode criar sua própria trilha "
            "sobre esse assunto com a ferramenta criar_minha_trilha."
        )

    votos = ctx.voto_repo.scores_por_materias([m.id for m in materias])
    linhas = []
    for m in materias:
        if m.owner_user_id is None:
            origem = "currículo oficial"
        elif m.owner_user_id == ctx.user_id:
            origem = "sua própria trilha"
        else:
            origem = f"trilha de outro aluno, votos={votos.get(m.id, 0)}"
        linhas.append(f"- {m.nome} (id={m.id}, {origem})")
    return "\n".join(linhas)


def _meu_desempenho(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    materia_nome = args.get("materia_nome")
    materias = ctx.materia_repo.list_minhas_e_globais_with_temas_e_modulos(ctx.user_id)
    if materia_nome:
        termo = materia_nome.strip().lower()
        materias = [m for m in materias if termo in m.nome.lower()]
        if not materias:
            return f"Nenhuma matéria encontrada com nome parecido com '{materia_nome}'."

    modulo_ids = [m.id for materia in materias for tema in materia.temas for m in tema.modulos]
    progresso_map = {
        p.modulo_id: p
        for p in ctx.progresso_repo.list_by_user_and_modulos(ctx.user_id, modulo_ids)
    }

    linhas = []
    for materia in materias:
        xp = ctx.xp_repo.total_por_usuario_e_materia(ctx.user_id, materia.id)
        concluidos = 0
        dificuldades = []
        for tema in materia.temas:
            for modulo in tema.modulos:
                progresso = progresso_map.get(modulo.id)
                if progresso is None or progresso.status != "concluido":
                    continue
                concluidos += 1
                if (
                    progresso.melhor_pontuacao is not None
                    and float(progresso.melhor_pontuacao) < _PONTUACAO_STRUGGLING
                ):
                    dificuldades.append(f"{modulo.titulo} ({progresso.melhor_pontuacao:.0f}%)")
        linha = f"- {materia.nome}: {xp} XP, {concluidos} módulo(s) concluído(s)"
        if dificuldades:
            linha += f"; dificuldade em: {', '.join(dificuldades)}"
        linhas.append(linha)

    if not linhas:
        return "O aluno ainda não tem nenhum progresso registrado."
    return "\n".join(linhas)


def _criar_minha_trilha(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    nome_materia = (args.get("nome_materia") or "").strip()
    titulo_tema = (args.get("titulo_tema") or "").strip()
    descricao_tema = args.get("descricao_tema")
    if not nome_materia or not titulo_tema:
        return "Informe nome_materia e titulo_tema."

    existente = next(
        (
            m
            for m in ctx.materia_repo.list_minhas_e_globais(ctx.user_id)
            if m.owner_user_id == ctx.user_id and m.nome.lower() == nome_materia.lower()
        ),
        None,
    )
    materia = existente or curriculo_service.criar_materia(
        nome_materia, None, ctx.materia_repo, owner_user_id=ctx.user_id
    )

    tema = curriculo_service.criar_tema_pendente(
        materia.id, titulo_tema, descricao_tema, ctx.materia_repo, ctx.tema_repo
    )
    ctx.materia_criada_id = materia.id
    ctx.tema_criado_id = tema.id

    if ctx.background_tasks is not None:
        ctx.background_tasks.add_task(
            trilha_pessoal_service.completar_criacao_trilha_pessoal,
            tema.id,
            ctx.pool_size,
            ctx.ai_provider,
        )
        aviso = (
            "Estou gerando o conteúdo e os módulos agora - isso leva alguns minutos; volte a "
            "esta conversa daqui a pouco, ou consulte GET /temas/{tema_id}/status, para "
            "conferir."
        )
    else:
        # No BackgroundTasks handed in (ctx built outside a real HTTP
        # request, e.g. a test) - do it inline rather than silently drop it.
        trilha_pessoal_service.completar_criacao_trilha_pessoal(
            tema.id, ctx.pool_size, ctx.ai_provider
        )
        aviso = "Conteúdo e módulos gerados."

    return (
        f"Criei a trilha '{materia.nome}' com o tema '{tema.titulo}' "
        f"(materia_id={materia.id}, tema_id={tema.id}). {aviso}"
    )


TOOLS: list[FerramentaDeclaracao] = [
    FerramentaDeclaracao(
        nome="buscar_conteudo",
        descricao=(
            "Busca, pelo nome/descrição, matérias sobre um assunto - tanto do currículo "
            "oficial quanto trilhas criadas por outros alunos (públicas e votáveis). Use "
            "antes de responder uma pergunta de assunto amplo, ou antes de oferecer criar "
            "uma trilha nova, para checar se já existe algo parecido."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {"termo": {"type": "STRING"}},
            "required": ["termo"],
        },
    ),
    FerramentaDeclaracao(
        nome="meu_desempenho",
        descricao=(
            "Retorna o XP e o progresso do aluno, opcionalmente filtrado por matéria - "
            "incluindo em quais módulos ele teve nota baixa (sinal de dificuldade). Use "
            "para adaptar a explicação ou sugerir o que revisar."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "materia_nome": {
                    "type": "STRING",
                    "description": "Opcional - filtra por uma matéria específica.",
                }
            },
        },
    ),
    FerramentaDeclaracao(
        nome="criar_minha_trilha",
        descricao=(
            "Cria uma trilha própria do aluno (matéria + tema) quando buscar_conteudo não "
            "encontrou nada satisfatório sobre o assunto. A geração do conteúdo roda em "
            "segundo plano - avise o aluno que vai levar um tempo, não prometa que já está "
            "pronto. A trilha fica pública e outros alunos podem votar nela."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "nome_materia": {
                    "type": "STRING",
                    "description": "Nome da matéria (ex.: 'Química Orgânica').",
                },
                "titulo_tema": {
                    "type": "STRING",
                    "description": "Título do primeiro tema dessa trilha.",
                },
                "descricao_tema": {"type": "STRING"},
            },
            "required": ["nome_materia", "titulo_tema"],
        },
    ),
]

_DISPATCH: dict[str, Callable[[dict[str, Any], FerramentaContexto], str]] = {
    "buscar_conteudo": _buscar_conteudo,
    "meu_desempenho": _meu_desempenho,
    "criar_minha_trilha": _criar_minha_trilha,
}


def executar_ferramenta_aluno(
    nome: str, argumentos: dict[str, Any], ctx: FerramentaContexto
) -> str:
    dispatch = _DISPATCH.get(nome)
    if dispatch is None:
        return f"Erro: ferramenta '{nome}' não existe."
    try:
        return dispatch(argumentos, ctx)
    except AppException as exc:
        return f"Erro: {exc.detail}"
    except (KeyError, ValueError) as exc:
        return f"Erro: argumentos inválidos para '{nome}': {exc}"
    except Exception as exc:  # noqa: BLE001 - never let one tool call crash the whole turn
        ctx.materia_repo.rollback()
        return f"Erro inesperado ao executar '{nome}': {exc}"
