"""Gemini-specific prompt templates.

Kept inside the concrete provider's concern (not a provider-agnostic location)
since prompt wording is tied to how this specific model responds. The
structured-output schemas for questionário/plano generation live in
`gemini_schemas.py`, not here - a schema isn't a prompt.
"""


AGENTE_ADMIN_SYSTEM_INSTRUCTION = """\
Você é o assistente de curadoria de conteúdo do ChatIn, um app de estudos para o \
ENEM organizado em matéria -> tema -> módulo. Um administrador te dá instruções em \
linguagem natural e você usa as ferramentas disponíveis para criar/editar/remover \
matérias, temas, módulos e questões.

Diretrizes para ser eficiente e evitar erros:
- Antes de assumir que algo não existe (uma matéria, um tema), verifique com \
listar_materias/listar_temas/listar_modulos em vez de perguntar ao usuário se já \
existe ou pedir para ele criar - você tem acesso direto a essa informação.
- Matérias (ex.: Matemática, Física) não têm ordem - são independentes entre si, \
não uma sequência. As ferramentas de matéria nem aceitam esse campo.
- Temas e módulos têm ordem, mas ela nunca é definida na criação: todo tema novo \
entra no final da lista de temas da matéria, e todo módulo novo entra no final da \
lista de módulos do tema - automaticamente, sem perguntar nada ao usuário. Só use \
o campo `ordem` de atualizar_tema/atualizar_modulo se o usuário pedir \
explicitamente para reordenar algo já existente (ex.: "coloque esse tema em \
primeiro").
- Só faça uma pergunta de esclarecimento quando a informação for realmente \
impossível de inferir e for necessária para prosseguir (ex.: título de um tema \
que o usuário não mencionou). Para tudo que tem um valor razoável por padrão, \
apenas prossiga.
- Ao criar um tema, lembre o usuário (ou apenas espere) que a pesquisa de fontes \
pode levar um instante antes do tema ficar "pronto" para receber módulos.
- Se o usuário pedir para mudar/melhorar/corrigir o conteúdo de um módulo já \
gerado (não um módulo novo), use regenerar_modulo passando o pedido dele no \
campo `instrucoes` - não tente reescrever o conteúdo você mesmo com \
editar_conteudo_modulo, a menos que o usuário peça uma edição pontual e \
específica (ex.: corrigir um erro de digitação).
- Seja direto e conciso nas respostas finais: confirme o que foi feito, não \
narre o processo interno de chamadas de ferramentas.
"""


def _direcionamento_texto(direcionamento: str | None) -> str:
    return (
        f" Siga também estas instruções do administrador: {direcionamento}"
        if direcionamento
        else ""
    )


def prompt_buscar_fontes(
    tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
) -> str:
    contexto = (
        f" Contexto adicional fornecido pelo administrador: {tema_descricao}"
        if tema_descricao
        else ""
    )
    return (
        "Você é um assistente educacional que prepara estudantes brasileiros para o ENEM. "
        f"Encontre de 3 a 5 fontes confiáveis e atuais sobre o tema '{tema_titulo}'.{contexto} "
        "Para cada fonte, produza um resumo objetivo de até 300 palavras do conteúdo relevante "
        "para um estudante do ensino médio se preparando para o ENEM."
        f"{_direcionamento_texto(direcionamento)} Responda em português."
    )


def prompt_gerar_conteudo_modulo(
    tema_titulo: str,
    modulo_titulo: str,
    modulo_descricao: str | None,
    conteudos_fontes: list[str],
    direcionamento: str | None = None,
    conteudo_ja_coberto: list[str] | None = None,
    instrucoes_regeneracao: str | None = None,
) -> str:
    fontes_texto = "\n\n---\n\n".join(conteudos_fontes)
    foco_texto = f" Foco específico deste módulo: {modulo_descricao}." if modulo_descricao else ""
    continuidade_texto = ""
    if conteudo_ja_coberto:
        coberto_texto = "\n\n---\n\n".join(conteudo_ja_coberto)
        continuidade_texto = (
            "\n\nIMPORTANTE - CONTINUIDADE: os módulos anteriores deste mesmo tema já "
            f"cobriram o seguinte conteúdo (NÃO repita o que já foi ensinado ali, "
            "continue a partir daqui, aprofundando ou avançando para os próximos "
            f"conceitos):\n\n{coberto_texto}"
        )
    ajustes_texto = ""
    if instrucoes_regeneracao:
        ajustes_texto = (
            "\n\nIMPORTANTE - AJUSTES SOLICITADOS: esta é uma regeneração do conteúdo deste "
            f"módulo. O administrador pediu especificamente: {instrucoes_regeneracao}. Gere a "
            "nova versão do conteúdo já incorporando esse pedido."
        )
    return (
        "Você é um professor preparando material de estudo. Com base exclusivamente nas fontes "
        f"abaixo sobre '{tema_titulo}', gere o conteúdo didático de um módulo de estudo chamado "
        f"'{modulo_titulo}'.{foco_texto} O conteúdo deve ser suficiente para ensinar os conceitos "
        "deste módulo especificamente (não o tema inteiro), de forma objetiva e didática, "
        f"organizado em tópicos com Markdown.{_direcionamento_texto(direcionamento)}"
        f"{continuidade_texto}{ajustes_texto} Responda em português.\n\n"
        f"FONTES:\n{fontes_texto}"
    )


def prompt_gerar_questionario(
    conteudo_modulo: str, foco_modulo: str | None, quantidade: int
) -> str:
    foco_texto = f" com foco específico em: {foco_modulo}." if foco_modulo else "."
    return (
        f"Com base no conteúdo do módulo abaixo, gere exatamente {quantidade} questões de múltipla "
        f"escolha no estilo ENEM{foco_texto} Cada questão deve ter exatamente 5 alternativas "
        "(A a E), apenas uma correta, e uma breve explicação didática da resposta correta. "
        "Os campos 'enunciado', o texto de cada alternativa e 'explicacao' devem ser uma única "
        "linha corrida cada (sem quebras de linha no meio do texto). Para notação matemática, "
        "use APENAS símbolos Unicode comuns (ex.: →, ∈, ≠, ≤, ≥, ², ³, √) ou expressões simples "
        "como 'x^2' - nunca comandos LaTeX com barra invertida (como \\to, \\in, \\neq), pois eles "
        "não são renderizados e quebram o texto. "
        "Responda em português.\n\n"
        f"CONTEÚDO:\n{conteudo_modulo}"
    )


def prompt_planejar_modulos(
    tema_titulo: str,
    tema_descricao: str | None,
    conteudos_fontes: list[str],
    max_modulos: int,
    direcionamento: str | None = None,
) -> str:
    fontes_texto = "\n\n---\n\n".join(conteudos_fontes)
    contexto = f" Contexto: {tema_descricao}." if tema_descricao else ""
    return (
        "Você é um professor planejando uma trilha de estudo. Com base exclusivamente nas fontes "
        f"abaixo sobre o tema '{tema_titulo}'{contexto}, proponha uma divisão do conteúdo em "
        "módulos de estudo sequenciais - use quantos módulos fizerem sentido para o conteúdo "
        f"disponível, mas NUNCA mais que {max_modulos} módulos. Cada módulo deve cobrir uma parte "
        "distinta e progressiva do assunto, sem sobreposição entre eles (o que o módulo 1 ensina "
        "não deve ser reensinado no módulo 2, e assim por diante). Para cada módulo, forneça um "
        "'titulo' curto e uma 'descricao' que resuma especificamente o foco daquele módulo (será "
        "usada depois para gerar o conteúdo detalhado dele)."
        f"{_direcionamento_texto(direcionamento)} Responda em "
        "português.\n\n"
        f"FONTES:\n{fontes_texto}"
    )
