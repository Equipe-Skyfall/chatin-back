"""Typed Python functions the Google ADK infers `FunctionTool`s from (via type
hints and docstrings), replacing the 21 hand-written JSON-schema dicts in
`app/services/agent_tools.py::TOOLS` - those stay as-is and keep serving the
legacy `GeminiProvider` path, which still needs to declare tools in that
uppercase-typed dialect for Gemini's native function-calling.

Every function here is a thin, typed pass-through to
`agent_tools.executar_ferramenta`, so both providers share the exact same
dispatch and error-handling logic (including the try/except-with-rollback
that never lets one tool call crash the whole turn) - nothing about *what a
tool does* is duplicated here, only *how the model is told to call it*.

`construir_tools(ctx)` builds these as nested closures over `ctx` (NOT via
`functools.partial`): ADK derives a tool's JSON schema straight from
`inspect.signature` of the callable it's given, and a bound
`functools.partial` keyword argument still shows up in that signature (with
a default value) - it does not get excluded from the schema shown to the
model. A closure has no such leak: `ctx` is a free variable, never a
parameter, so it's structurally impossible for the model to see or set it.
"""

from collections.abc import Callable

from app.ai.adk_schemas import AlternativaSchema, Letra
from app.ai.schemas import FerramentaContexto
from app.services.agent_tools import executar_ferramenta
from app.services.agent_tools_aluno import executar_ferramenta_aluno


def construir_tools(ctx: FerramentaContexto) -> list[Callable]:
    """Returns the admin agent's 21 tools as closures over `ctx` - called
    fresh per `conversar_com_ferramentas` call, since `ctx` (repos,
    ai_provider) is itself per-request."""

    def listar_materias() -> str:
        """Lista todas as matérias cadastradas, com seus ids."""
        return executar_ferramenta("listar_materias", {}, ctx)

    def criar_materia(nome: str, descricao: str | None = None) -> str:
        """Cria uma nova matéria (ex.: 'Matemática'). Matérias não têm ordem -
        são independentes entre si, não uma sequência.

        Args:
            nome: Nome da matéria.
            descricao: Descrição opcional da matéria.
        """
        return executar_ferramenta("criar_materia", {"nome": nome, "descricao": descricao}, ctx)

    def atualizar_materia(
        materia_id: str, nome: str | None = None, descricao: str | None = None
    ) -> str:
        """Edita o nome/descrição de uma matéria existente."""
        return executar_ferramenta(
            "atualizar_materia",
            {"materia_id": materia_id, "nome": nome, "descricao": descricao},
            ctx,
        )

    def deletar_materia(materia_id: str) -> str:
        """Remove uma matéria e tudo dentro dela (temas, módulos,
        questionários)."""
        return executar_ferramenta("deletar_materia", {"materia_id": materia_id}, ctx)

    def listar_temas(materia_id: str) -> str:
        """Lista os temas de uma matéria, com seus ids e status."""
        return executar_ferramenta("listar_temas", {"materia_id": materia_id}, ctx)

    def criar_tema(
        materia_id: str,
        titulo: str,
        descricao: str | None = None,
        direcionamento: str | None = None,
    ) -> str:
        """Cria um novo tema dentro de uma matéria (ex.: 'Cálculo 1' em
        'Matemática'). Sempre é adicionado ao final da lista de temas dessa
        matéria - para mudar a posição depois, use atualizar_tema. Isso
        dispara automaticamente uma pesquisa de fontes sobre o tema -
        aguarde o tema ficar com status 'pronto' antes de criar módulos
        nele.

        Args:
            direcionamento: Instruções livres para a IA usar ao gerar
                conteúdo deste tema (ex.: 'use exemplos práticos', 'foque em
                aplicações do ENEM').
        """
        return executar_ferramenta(
            "criar_tema",
            {
                "materia_id": materia_id,
                "titulo": titulo,
                "descricao": descricao,
                "direcionamento": direcionamento,
            },
            ctx,
        )

    def atualizar_tema(
        materia_id: str,
        tema_id: str,
        titulo: str | None = None,
        descricao: str | None = None,
        ordem: int | None = None,
        direcionamento: str | None = None,
    ) -> str:
        """Edita título/descrição/direcionamento de um tema (não afeta suas
        fontes), e/ou move sua posição (`ordem`) dentro da matéria - só
        informe `ordem` se o usuário pedir explicitamente para reordenar."""
        return executar_ferramenta(
            "atualizar_tema",
            {
                "materia_id": materia_id,
                "tema_id": tema_id,
                "titulo": titulo,
                "descricao": descricao,
                "ordem": ordem,
                "direcionamento": direcionamento,
            },
            ctx,
        )

    def deletar_tema(materia_id: str, tema_id: str) -> str:
        """Remove um tema e todos os seus módulos."""
        return executar_ferramenta(
            "deletar_tema", {"materia_id": materia_id, "tema_id": tema_id}, ctx
        )

    def regenerar_tema(materia_id: str, tema_id: str) -> str:
        """Pesquisa as fontes do tema novamente do zero (substitui as fontes
        existentes)."""
        return executar_ferramenta(
            "regenerar_tema", {"materia_id": materia_id, "tema_id": tema_id}, ctx
        )

    def dividir_tema_em_modulos(tema_id: str) -> str:
        """Divide automaticamente um tema (que já esteja com status 'pronto'
        e ainda sem nenhum módulo) em até 5 módulos: a IA propõe os
        títulos/focos e gera o conteúdo + questionário de cada um, em ordem,
        sem repetir entre eles. Só funciona se o tema ainda não tiver
        módulos - use criar_modulo para adicionar módulos manualmente em
        outros casos."""
        return executar_ferramenta("dividir_tema_em_modulos", {"tema_id": tema_id}, ctx)

    def listar_modulos(tema_id: str) -> str:
        """Lista os módulos de um tema, com seus ids e status."""
        return executar_ferramenta("listar_modulos", {"tema_id": tema_id}, ctx)

    def criar_modulo(
        tema_id: str,
        titulo: str,
        descricao: str | None = None,
        conteudo: str | None = None,
    ) -> str:
        """Cria um módulo dentro de um tema (o tema precisa estar com status
        'pronto'). Sempre é adicionado ao final da lista de módulos desse
        tema - para mudar a posição depois, use atualizar_modulo. Por
        padrão gera automaticamente o conteúdo didático do módulo (a partir
        das fontes do tema e da descrição/foco deste módulo); se o usuário
        fornecer o `conteudo` já pronto (escrito por ele), esse texto é
        usado no lugar - a IA só gera o questionário de múltipla escolha a
        partir dele. Para quebrar um tema em vários módulos, chame esta
        ferramenta uma vez por módulo, com título/descrição descrevendo o
        foco de cada um.

        Args:
            descricao: O foco específico deste módulo.
            conteudo: Conteúdo didático já escrito pelo usuário. Se
                informado, a IA NÃO gera o conteúdo - só o questionário, a
                partir deste texto.
        """
        return executar_ferramenta(
            "criar_modulo",
            {"tema_id": tema_id, "titulo": titulo, "descricao": descricao, "conteudo": conteudo},
            ctx,
        )

    def atualizar_modulo(
        tema_id: str,
        modulo_id: str,
        titulo: str | None = None,
        descricao: str | None = None,
        ordem: int | None = None,
    ) -> str:
        """Edita título/descrição de um módulo (não regenera conteúdo/
        questionário), e/ou move sua posição (`ordem`) dentro do tema - só
        informe `ordem` se o usuário pedir explicitamente para reordenar."""
        return executar_ferramenta(
            "atualizar_modulo",
            {
                "tema_id": tema_id,
                "modulo_id": modulo_id,
                "titulo": titulo,
                "descricao": descricao,
                "ordem": ordem,
            },
            ctx,
        )

    def deletar_modulo(tema_id: str, modulo_id: str) -> str:
        """Remove um módulo, seu conteúdo e seu questionário."""
        return executar_ferramenta(
            "deletar_modulo", {"tema_id": tema_id, "modulo_id": modulo_id}, ctx
        )

    def regenerar_modulo(
        tema_id: str, modulo_id: str, instrucoes: str | None = None
    ) -> str:
        """Regenera o conteúdo e o questionário de um módulo (nova chamada
        de IA), descartando a versão atual. Use `instrucoes` para guiar a
        regeneração com o pedido específico do usuário (ex.: 'deixe mais
        curto', 'adicione mais exemplos práticos', 'explique melhor o
        conceito X') - sem isso, é uma regeneração do zero sem direção
        específica.

        Args:
            instrucoes: O que mudar em relação à versão atual, nas palavras
                do usuário.
        """
        return executar_ferramenta(
            "regenerar_modulo",
            {"tema_id": tema_id, "modulo_id": modulo_id, "instrucoes": instrucoes},
            ctx,
        )

    def regenerar_questionario_modulo(tema_id: str, modulo_id: str) -> str:
        """Gera um questionário novo (nova chamada de IA) para um módulo,
        mantendo o conteúdo didático como está - use quando o usuário só
        quer questões novas/diferentes, sem mudar o que o módulo ensina.
        Para mudar o conteúdo também, use regenerar_modulo."""
        return executar_ferramenta(
            "regenerar_questionario_modulo", {"tema_id": tema_id, "modulo_id": modulo_id}, ctx
        )

    def regenerar_questionarios_tema(tema_id: str) -> str:
        """Gera um questionário novo para TODOS os módulos de um tema que já
        têm conteúdo (uma chamada de IA por módulo, conteúdo mantido) - use
        quando o usuário pedir para renovar/criar questionários novos para
        um tema inteiro, não só um módulo específico."""
        return executar_ferramenta("regenerar_questionarios_tema", {"tema_id": tema_id}, ctx)

    def obter_conteudo_modulo(modulo_id: str) -> str:
        """Lê o conteúdo didático já gerado/armazenado de um módulo."""
        return executar_ferramenta("obter_conteudo_modulo", {"modulo_id": modulo_id}, ctx)

    def editar_conteudo_modulo(modulo_id: str, conteudo: str) -> str:
        """Substitui manualmente o conteúdo de um módulo (sem chamar IA)."""
        return executar_ferramenta(
            "editar_conteudo_modulo", {"modulo_id": modulo_id, "conteudo": conteudo}, ctx
        )

    def listar_questoes(modulo_id: str) -> str:
        """Lista as questões de um módulo, incluindo a resposta correta de
        cada uma."""
        return executar_ferramenta("listar_questoes", {"modulo_id": modulo_id}, ctx)

    def editar_questao(
        modulo_id: str,
        questao_id: str,
        enunciado: str | None = None,
        alternativas: list[AlternativaSchema] | None = None,
        explicacao: str | None = None,
        resposta_correta: Letra | None = None,
    ) -> str:
        """Corrige manualmente uma questão (enunciado, alternativas e/ou
        resposta). Quando informadas, `alternativas` deve ter exatamente 5
        itens."""
        return executar_ferramenta(
            "editar_questao",
            {
                "modulo_id": modulo_id,
                "questao_id": questao_id,
                "enunciado": enunciado,
                "alternativas": (
                    [a.model_dump() for a in alternativas]
                    if alternativas is not None
                    else None
                ),
                "explicacao": explicacao,
                "resposta_correta": resposta_correta,
            },
            ctx,
        )

    return [
        listar_materias,
        criar_materia,
        atualizar_materia,
        deletar_materia,
        listar_temas,
        criar_tema,
        atualizar_tema,
        deletar_tema,
        regenerar_tema,
        dividir_tema_em_modulos,
        listar_modulos,
        criar_modulo,
        atualizar_modulo,
        deletar_modulo,
        regenerar_modulo,
        regenerar_questionario_modulo,
        regenerar_questionarios_tema,
        obter_conteudo_modulo,
        editar_conteudo_modulo,
        listar_questoes,
        editar_questao,
    ]


def construir_tools_aluno(ctx: FerramentaContexto) -> list[Callable]:
    """The student agent's 3 tools, same closure-over-`ctx` shape as
    `construir_tools` above - see its docstring for why a closure and not
    `functools.partial`."""

    def buscar_conteudo(termo: str) -> str:
        """Busca, pelo nome/descrição, matérias sobre um assunto - tanto do
        currículo oficial quanto trilhas criadas por outros alunos (públicas
        e votáveis). Use antes de responder uma pergunta de assunto amplo,
        ou antes de oferecer criar uma trilha nova, para checar se já existe
        algo parecido.

        Args:
            termo: O que buscar (ex.: 'cálculo', 'funções quadráticas').
        """
        return executar_ferramenta_aluno("buscar_conteudo", {"termo": termo}, ctx)

    def meu_desempenho(materia_nome: str | None = None) -> str:
        """Retorna o XP e o progresso do aluno, opcionalmente filtrado por
        matéria - incluindo em quais módulos ele teve nota baixa (sinal de
        dificuldade). Use para adaptar a explicação ou sugerir o que
        revisar.

        Args:
            materia_nome: Opcional - filtra por uma matéria específica.
        """
        return executar_ferramenta_aluno(
            "meu_desempenho", {"materia_nome": materia_nome}, ctx
        )

    def criar_minha_trilha(
        nome_materia: str, titulo_tema: str, descricao_tema: str | None = None
    ) -> str:
        """Cria uma trilha própria do aluno (matéria + tema) quando
        buscar_conteudo não encontrou nada satisfatório sobre o assunto. A
        geração do conteúdo roda em segundo plano - avise o aluno que vai
        levar um tempo, não prometa que já está pronto. A trilha fica
        pública e outros alunos podem votar nela.

        Args:
            nome_materia: Nome da matéria (ex.: 'Química Orgânica').
            titulo_tema: Título do primeiro tema dessa trilha.
            descricao_tema: Descrição opcional do foco desse tema.
        """
        return executar_ferramenta_aluno(
            "criar_minha_trilha",
            {
                "nome_materia": nome_materia,
                "titulo_tema": titulo_tema,
                "descricao_tema": descricao_tema,
            },
            ctx,
        )

    return [buscar_conteudo, meu_desempenho, criar_minha_trilha]
