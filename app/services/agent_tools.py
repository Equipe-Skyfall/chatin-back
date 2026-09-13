"""The agent's tool registry: one tool per admin operation, each a thin
wrapper around `curriculo_service` (or a read-only repository lookup) - the
same functions the REST routers call. Full parity with the REST API by
construction: nothing here duplicates business logic, it only translates
between Gemini's function-call args and `curriculo_service`'s parameters.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.base import AIProvider
from app.ai.schemas import FerramentaDeclaracao
from app.core.exceptions import AppException
from app.repositories.materia_repository import MateriaRepository
from app.repositories.modulo_repository import ModuloRepository
from app.repositories.questionario_repository import QuestionarioRepository
from app.repositories.tema_repository import TemaRepository
from app.services import curriculo_service


@dataclass
class FerramentaContexto:
    materia_repo: MateriaRepository
    tema_repo: TemaRepository
    modulo_repo: ModuloRepository
    questionario_repo: QuestionarioRepository
    ai_provider: AIProvider
    pool_size: int


def _uid(valor: str) -> uuid.UUID:
    return uuid.UUID(valor)


# --- Matéria ---


def _criar_materia(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    materia = curriculo_service.criar_materia(
        args["nome"], args.get("descricao"), ctx.materia_repo
    )
    return f"Matéria '{materia.nome}' criada (id={materia.id})."


def _atualizar_materia(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    materia = curriculo_service.atualizar_materia(
        _uid(args["materia_id"]),
        args.get("nome"),
        args.get("descricao"),
        ctx.materia_repo,
    )
    return f"Matéria '{materia.nome}' (id={materia.id}) atualizada."


def _deletar_materia(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    curriculo_service.deletar_materia(_uid(args["materia_id"]), ctx.materia_repo)
    return f"Matéria {args['materia_id']} removida, com tudo o que havia dentro dela."


def _listar_materias(_args: dict[str, Any], ctx: FerramentaContexto) -> str:
    materias = ctx.materia_repo.list_globais()
    if not materias:
        return "Nenhuma matéria cadastrada ainda."
    return "\n".join(f"- {m.nome} (id={m.id})" for m in materias)


# --- Tema ---


def _criar_tema(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    tema = curriculo_service.criar_tema(
        _uid(args["materia_id"]),
        args["titulo"],
        args.get("descricao"),
        ctx.materia_repo,
        ctx.tema_repo,
        ctx.ai_provider,
        direcionamento=args.get("direcionamento"),
    )
    return f"Tema '{tema.titulo}' criado (id={tema.id}, ordem={tema.ordem}), status={tema.status}."


def _atualizar_tema(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    tema = curriculo_service.atualizar_tema(
        _uid(args["materia_id"]),
        _uid(args["tema_id"]),
        args.get("titulo"),
        args.get("descricao"),
        args.get("ordem"),
        ctx.tema_repo,
        args.get("direcionamento"),
    )
    return f"Tema '{tema.titulo}' (id={tema.id}) atualizado."


def _dividir_tema_em_modulos(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulos = curriculo_service.dividir_tema_em_modulos(
        _uid(args["tema_id"]),
        ctx.pool_size,
        ctx.tema_repo,
        ctx.modulo_repo,
        ctx.questionario_repo,
        ctx.ai_provider,
    )
    if not modulos:
        return "A IA não conseguiu propor nenhum módulo para este tema."
    linhas = "\n".join(f"- {m.titulo} (id={m.id}, status={m.status})" for m in modulos)
    return f"{len(modulos)} módulo(s) gerados automaticamente:\n{linhas}"


def _deletar_tema(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    curriculo_service.deletar_tema(_uid(args["materia_id"]), _uid(args["tema_id"]), ctx.tema_repo)
    return f"Tema {args['tema_id']} removido, com todos os seus módulos."


def _regenerar_tema(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    tema = curriculo_service.regenerar_tema(
        _uid(args["materia_id"]), _uid(args["tema_id"]), ctx.tema_repo, ctx.ai_provider
    )
    return f"Fontes do tema '{tema.titulo}' pesquisadas novamente, status={tema.status}."


def _listar_temas(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    temas = ctx.tema_repo.list_by_materia(_uid(args["materia_id"]))
    if not temas:
        return "Esta matéria ainda não tem temas."
    return "\n".join(f"- {t.titulo} (id={t.id}, ordem={t.ordem}, status={t.status})" for t in temas)


# --- Módulo ---


def _criar_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = curriculo_service.criar_modulo(
        _uid(args["tema_id"]),
        args["titulo"],
        args.get("descricao"),
        ctx.pool_size,
        ctx.tema_repo,
        ctx.modulo_repo,
        ctx.questionario_repo,
        ctx.ai_provider,
        conteudo=args.get("conteudo"),
    )
    return (
        f"Módulo '{modulo.titulo}' criado (id={modulo.id}, ordem={modulo.ordem}), "
        f"status={modulo.status}."
    )


def _atualizar_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = curriculo_service.atualizar_modulo(
        _uid(args["tema_id"]),
        _uid(args["modulo_id"]),
        args.get("titulo"),
        args.get("descricao"),
        args.get("ordem"),
        ctx.modulo_repo,
    )
    return f"Módulo '{modulo.titulo}' (id={modulo.id}) atualizado."


def _deletar_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    curriculo_service.deletar_modulo(
        _uid(args["tema_id"]), _uid(args["modulo_id"]), ctx.modulo_repo
    )
    return f"Módulo {args['modulo_id']} removido, com seu conteúdo e questionário."


def _regenerar_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = curriculo_service.regenerar_modulo(
        _uid(args["tema_id"]),
        _uid(args["modulo_id"]),
        ctx.pool_size,
        ctx.tema_repo,
        ctx.modulo_repo,
        ctx.questionario_repo,
        ctx.ai_provider,
        instrucoes=args.get("instrucoes"),
    )
    return f"Módulo '{modulo.titulo}' regenerado (conteúdo + questionário), status={modulo.status}."


def _regenerar_questionario_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = curriculo_service.regenerar_questionario_modulo(
        _uid(args["tema_id"]),
        _uid(args["modulo_id"]),
        ctx.pool_size,
        ctx.modulo_repo,
        ctx.questionario_repo,
        ctx.ai_provider,
    )
    return f"Questionário do módulo '{modulo.titulo}' regenerado (conteúdo não foi alterado)."


def _regenerar_questionarios_tema(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulos = curriculo_service.regenerar_questionarios_tema(
        _uid(args["tema_id"]),
        ctx.pool_size,
        ctx.tema_repo,
        ctx.modulo_repo,
        ctx.questionario_repo,
        ctx.ai_provider,
    )
    if not modulos:
        return "Nenhum módulo deste tema tinha conteúdo pronto para gerar um novo questionário."
    linhas = "\n".join(f"- {m.titulo}" for m in modulos)
    return f"Questionário regenerado para {len(modulos)} módulo(s):\n{linhas}"


def _listar_modulos(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulos = ctx.modulo_repo.list_by_tema(_uid(args["tema_id"]))
    if not modulos:
        return "Este tema ainda não tem módulos."
    return "\n".join(
        f"- {m.titulo} (id={m.id}, ordem={m.ordem}, status={m.status})" for m in modulos
    )


def _obter_conteudo_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = ctx.modulo_repo.get(_uid(args["modulo_id"]))
    if modulo is None:
        return f"Módulo {args['modulo_id']} não encontrado."
    return modulo.conteudo or "(este módulo ainda não tem conteúdo gerado)"


def _editar_conteudo_modulo(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    modulo = curriculo_service.editar_conteudo_modulo(
        _uid(args["modulo_id"]), args["conteudo"], ctx.modulo_repo
    )
    return f"Conteúdo do módulo '{modulo.titulo}' atualizado manualmente."


# --- Questão ---


def _listar_questoes(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    questionario = ctx.questionario_repo.get_by_modulo(_uid(args["modulo_id"]))
    if questionario is None:
        return "Este módulo ainda não tem questionário gerado."
    ids = ctx.questionario_repo.get_questao_ids_pool(questionario.id)
    questoes = sorted(ctx.questionario_repo.get_questoes_by_ids(ids), key=lambda q: q.ordem)
    gabarito = ctx.questionario_repo.get_gabarito_map(ids)
    linhas = []
    for q in questoes:
        alts = ", ".join(f"{a['letra']}) {a['texto']}" for a in q.alternativas)
        linhas.append(f"- id={q.id} | {q.enunciado} | {alts} | correta={gabarito[q.id]}")
    return "\n".join(linhas)


def _editar_questao(args: dict[str, Any], ctx: FerramentaContexto) -> str:
    alternativas = args.get("alternativas")
    questao, resposta_correta = curriculo_service.editar_questao(
        _uid(args["modulo_id"]),
        _uid(args["questao_id"]),
        args.get("enunciado"),
        alternativas,
        args.get("explicacao"),
        args.get("resposta_correta"),
        ctx.modulo_repo,
        ctx.questionario_repo,
    )
    return f"Questão {questao.id} atualizada (resposta correta: {resposta_correta})."


_ALTERNATIVA_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "letra": {"type": "STRING", "enum": ["A", "B", "C", "D", "E"]},
        "texto": {"type": "STRING"},
    },
    "required": ["letra", "texto"],
}

TOOLS: list[FerramentaDeclaracao] = [
    FerramentaDeclaracao(
        nome="listar_materias",
        descricao="Lista todas as matérias cadastradas, com seus ids.",
        parametros={"type": "OBJECT", "properties": {}},
    ),
    FerramentaDeclaracao(
        nome="criar_materia",
        descricao=(
            "Cria uma nova matéria (ex.: 'Matemática'). Matérias não têm ordem - são "
            "independentes entre si, não uma sequência."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "nome": {"type": "STRING"},
                "descricao": {"type": "STRING"},
            },
            "required": ["nome"],
        },
    ),
    FerramentaDeclaracao(
        nome="atualizar_materia",
        descricao="Edita o nome/descrição de uma matéria existente.",
        parametros={
            "type": "OBJECT",
            "properties": {
                "materia_id": {"type": "STRING"},
                "nome": {"type": "STRING"},
                "descricao": {"type": "STRING"},
            },
            "required": ["materia_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="deletar_materia",
        descricao="Remove uma matéria e tudo dentro dela (temas, módulos, questionários).",
        parametros={
            "type": "OBJECT",
            "properties": {"materia_id": {"type": "STRING"}},
            "required": ["materia_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="listar_temas",
        descricao="Lista os temas de uma matéria, com seus ids e status.",
        parametros={
            "type": "OBJECT",
            "properties": {"materia_id": {"type": "STRING"}},
            "required": ["materia_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="criar_tema",
        descricao=(
            "Cria um novo tema dentro de uma matéria (ex.: 'Cálculo 1' em 'Matemática'). "
            "Sempre é adicionado ao final da lista de temas dessa matéria - para mudar a "
            "posição depois, use atualizar_tema. Isso dispara automaticamente uma pesquisa "
            "de fontes sobre o tema - aguarde o tema ficar com status 'pronto' antes de "
            "criar módulos nele."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "materia_id": {"type": "STRING"},
                "titulo": {"type": "STRING"},
                "descricao": {"type": "STRING"},
                "direcionamento": {
                    "type": "STRING",
                    "description": (
                        "Instruções livres para a IA usar ao gerar conteúdo deste tema "
                        "(ex.: 'use exemplos práticos', 'foque em aplicações do ENEM')."
                    ),
                },
            },
            "required": ["materia_id", "titulo"],
        },
    ),
    FerramentaDeclaracao(
        nome="atualizar_tema",
        descricao=(
            "Edita título/descrição/direcionamento de um tema (não afeta suas fontes), e/ou "
            "move sua posição (`ordem`) dentro da matéria - só informe `ordem` se o usuário "
            "pedir explicitamente para reordenar."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "materia_id": {"type": "STRING"},
                "tema_id": {"type": "STRING"},
                "titulo": {"type": "STRING"},
                "descricao": {"type": "STRING"},
                "ordem": {"type": "INTEGER"},
                "direcionamento": {"type": "STRING"},
            },
            "required": ["materia_id", "tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="deletar_tema",
        descricao="Remove um tema e todos os seus módulos.",
        parametros={
            "type": "OBJECT",
            "properties": {"materia_id": {"type": "STRING"}, "tema_id": {"type": "STRING"}},
            "required": ["materia_id", "tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="regenerar_tema",
        descricao="Pesquisa as fontes do tema novamente do zero (substitui as fontes existentes).",
        parametros={
            "type": "OBJECT",
            "properties": {"materia_id": {"type": "STRING"}, "tema_id": {"type": "STRING"}},
            "required": ["materia_id", "tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="dividir_tema_em_modulos",
        descricao=(
            "Divide automaticamente um tema (que já esteja com status 'pronto' e ainda "
            "sem nenhum módulo) em até 5 módulos: a IA propõe os títulos/focos e gera o "
            "conteúdo + questionário de cada um, em ordem, sem repetir entre eles. Só "
            "funciona se o tema ainda não tiver módulos - use criar_modulo para adicionar "
            "módulos manualmente em outros casos."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {"tema_id": {"type": "STRING"}},
            "required": ["tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="listar_modulos",
        descricao="Lista os módulos de um tema, com seus ids e status.",
        parametros={
            "type": "OBJECT",
            "properties": {"tema_id": {"type": "STRING"}},
            "required": ["tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="criar_modulo",
        descricao=(
            "Cria um módulo dentro de um tema (o tema precisa estar com status 'pronto'). "
            "Sempre é adicionado ao final da lista de módulos desse tema - para mudar a "
            "posição depois, use atualizar_modulo. Por padrão gera automaticamente o "
            "conteúdo didático do módulo (a partir das fontes do tema e da descrição/foco "
            "deste módulo); se o usuário fornecer o `conteudo` já pronto (escrito por ele), "
            "esse texto é usado no lugar - a IA só gera o questionário de múltipla escolha "
            "a partir dele. Para quebrar um tema em vários módulos, chame esta ferramenta "
            "uma vez por módulo, com título/descrição descrevendo o foco de cada um."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "tema_id": {"type": "STRING"},
                "titulo": {"type": "STRING"},
                "descricao": {"type": "STRING", "description": "O foco específico deste módulo."},
                "conteudo": {
                    "type": "STRING",
                    "description": (
                        "Conteúdo didático já escrito pelo usuário. Se informado, a IA NÃO "
                        "gera o conteúdo - só o questionário, a partir deste texto."
                    ),
                },
            },
            "required": ["tema_id", "titulo"],
        },
    ),
    FerramentaDeclaracao(
        nome="atualizar_modulo",
        descricao=(
            "Edita título/descrição de um módulo (não regenera conteúdo/questionário), e/ou "
            "move sua posição (`ordem`) dentro do tema - só informe `ordem` se o usuário "
            "pedir explicitamente para reordenar."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "tema_id": {"type": "STRING"},
                "modulo_id": {"type": "STRING"},
                "titulo": {"type": "STRING"},
                "descricao": {"type": "STRING"},
                "ordem": {"type": "INTEGER"},
            },
            "required": ["tema_id", "modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="deletar_modulo",
        descricao="Remove um módulo, seu conteúdo e seu questionário.",
        parametros={
            "type": "OBJECT",
            "properties": {"tema_id": {"type": "STRING"}, "modulo_id": {"type": "STRING"}},
            "required": ["tema_id", "modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="regenerar_modulo",
        descricao=(
            "Regenera o conteúdo e o questionário de um módulo (nova chamada de IA), "
            "descartando a versão atual. Use `instrucoes` para guiar a regeneração com o "
            "pedido específico do usuário (ex.: 'deixe mais curto', 'adicione mais "
            "exemplos práticos', 'explique melhor o conceito X') - sem isso, é uma "
            "regeneração do zero sem direção específica."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "tema_id": {"type": "STRING"},
                "modulo_id": {"type": "STRING"},
                "instrucoes": {
                    "type": "STRING",
                    "description": (
                        "O que mudar em relação à versão atual, nas palavras do usuário."
                    ),
                },
            },
            "required": ["tema_id", "modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="regenerar_questionario_modulo",
        descricao=(
            "Gera um questionário novo (nova chamada de IA) para um módulo, mantendo o "
            "conteúdo didático como está - use quando o usuário só quer questões novas/"
            "diferentes, sem mudar o que o módulo ensina. Para mudar o conteúdo também, "
            "use regenerar_modulo."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {
                "tema_id": {"type": "STRING"},
                "modulo_id": {"type": "STRING"},
            },
            "required": ["tema_id", "modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="regenerar_questionarios_tema",
        descricao=(
            "Gera um questionário novo para TODOS os módulos de um tema que já têm "
            "conteúdo (uma chamada de IA por módulo, conteúdo mantido) - use quando o "
            "usuário pedir para renovar/criar questionários novos para um tema inteiro, "
            "não só um módulo específico."
        ),
        parametros={
            "type": "OBJECT",
            "properties": {"tema_id": {"type": "STRING"}},
            "required": ["tema_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="obter_conteudo_modulo",
        descricao="Lê o conteúdo didático já gerado/armazenado de um módulo.",
        parametros={
            "type": "OBJECT",
            "properties": {"modulo_id": {"type": "STRING"}},
            "required": ["modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="editar_conteudo_modulo",
        descricao="Substitui manualmente o conteúdo de um módulo (sem chamar IA).",
        parametros={
            "type": "OBJECT",
            "properties": {"modulo_id": {"type": "STRING"}, "conteudo": {"type": "STRING"}},
            "required": ["modulo_id", "conteudo"],
        },
    ),
    FerramentaDeclaracao(
        nome="listar_questoes",
        descricao="Lista as questões de um módulo, incluindo a resposta correta de cada uma.",
        parametros={
            "type": "OBJECT",
            "properties": {"modulo_id": {"type": "STRING"}},
            "required": ["modulo_id"],
        },
    ),
    FerramentaDeclaracao(
        nome="editar_questao",
        descricao="Corrige manualmente uma questão (enunciado, alternativas e/ou resposta).",
        parametros={
            "type": "OBJECT",
            "properties": {
                "modulo_id": {"type": "STRING"},
                "questao_id": {"type": "STRING"},
                "enunciado": {"type": "STRING"},
                "alternativas": {
                    "type": "ARRAY",
                    # google-genai's FunctionDeclaration validates this against its own
                    # Schema type, where minItems/maxItems are typed as `str`, not `int`
                    # (unlike the `response_schema` config, which is more lenient about it).
                    "minItems": "5",
                    "maxItems": "5",
                    "items": _ALTERNATIVA_SCHEMA,
                },
                "explicacao": {"type": "STRING"},
                "resposta_correta": {"type": "STRING", "enum": ["A", "B", "C", "D", "E"]},
            },
            "required": ["modulo_id", "questao_id"],
        },
    ),
]

_DISPATCH: dict[str, Callable[[dict[str, Any], FerramentaContexto], str]] = {
    "listar_materias": _listar_materias,
    "criar_materia": _criar_materia,
    "atualizar_materia": _atualizar_materia,
    "deletar_materia": _deletar_materia,
    "listar_temas": _listar_temas,
    "criar_tema": _criar_tema,
    "atualizar_tema": _atualizar_tema,
    "deletar_tema": _deletar_tema,
    "regenerar_tema": _regenerar_tema,
    "dividir_tema_em_modulos": _dividir_tema_em_modulos,
    "listar_modulos": _listar_modulos,
    "criar_modulo": _criar_modulo,
    "atualizar_modulo": _atualizar_modulo,
    "deletar_modulo": _deletar_modulo,
    "regenerar_modulo": _regenerar_modulo,
    "regenerar_questionario_modulo": _regenerar_questionario_modulo,
    "regenerar_questionarios_tema": _regenerar_questionarios_tema,
    "obter_conteudo_modulo": _obter_conteudo_modulo,
    "editar_conteudo_modulo": _editar_conteudo_modulo,
    "listar_questoes": _listar_questoes,
    "editar_questao": _editar_questao,
}


def executar_ferramenta(nome: str, argumentos: dict[str, Any], ctx: FerramentaContexto) -> str:
    dispatch = _DISPATCH.get(nome)
    if dispatch is None:
        return f"Erro: ferramenta '{nome}' não existe."
    try:
        return dispatch(argumentos, ctx)
    except AppException as exc:
        return f"Erro: {exc.detail}"
    except (KeyError, ValueError) as exc:
        return f"Erro: argumentos inválidos para '{nome}': {exc}"
    except Exception as exc:  # noqa: BLE001 - last resort: never let one tool call
        # crash the whole /admin/chat request (and poison the shared DB session
        # for every tool call still left in this turn's loop).
        ctx.materia_repo.rollback()
        return f"Erro inesperado ao executar '{nome}': {exc}"
