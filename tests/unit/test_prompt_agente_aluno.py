"""`prompt_agente_aluno_system` is the only place in the codebase that embeds
AI-generated, per-turn text into an ADK agent's `instruction=` string - every
other agent's instruction is static. The ADK treats `{identifier}` inside an
instruction as a session-state template variable and raises `KeyError` (502
for the whole chat turn) when that identifier isn't an actual state key - see
`google.adk.utils.instructions_utils`. A módulo's content routinely contains
a bare `{x}` (algebra, calculus...), so this reproduces the exact regex/
identifier logic ADK applies, rather than just asserting our own escaping."""

import re

from app.ai.prompts import prompt_agente_aluno_system

# Copied from google.adk.utils.instructions_utils - kept in sync deliberately
# (not imported) so this test fails loudly if the installed ADK's own
# template regex ever changes, instead of silently testing against nothing.
_TEMPLATE_VAR_PATTERN = re.compile(r"{+[^{}]*}+")


def _tem_variavel_de_template_adk(texto: str) -> bool:
    """True if the ADK's own regex would find a `{bare_identifier}` in `texto`
    that isn't a real session-state key - i.e. would raise `KeyError` and 502
    the chat turn."""
    for match in _TEMPLATE_VAR_PATTERN.finditer(texto):
        var_name = match.group().lstrip("{").rstrip("}").strip()
        if var_name.isidentifier():
            return True
    return False


def test_conteudo_com_variavel_de_algebra_nao_quebra_a_instrucao_do_adk():
    prompt = prompt_agente_aluno_system("Resolva a equação para {x}: 2{x} + 3 = 7.")

    assert not _tem_variavel_de_template_adk(prompt)
    # ainda legível/reconhecível pro modelo - só a chave ASCII muda
    assert "x" in prompt
    assert "{x}" not in prompt


def test_conteudo_sem_chaves_fica_identico():
    prompt = prompt_agente_aluno_system("Cálculo 1 trata de limites e derivadas.")

    assert "Cálculo 1 trata de limites e derivadas." in prompt


def test_conteudo_none_nao_menciona_modulo_especifico():
    prompt = prompt_agente_aluno_system(None)

    assert "não abriu esta conversa a partir de um módulo específico" in prompt


def test_conteudo_com_chaves_mas_sem_identificador_bare_ja_seria_seguro():
    """Confirma o entendimento do bug: chaves com espaço/pontuação dentro nunca
    quebravam (a ADK só levanta erro pra um identificador puro) - só documenta
    isso, não depende do nosso escape pra ficar seguro."""
    texto = "O conjunto {1, 2, 3} e o domínio {x ∈ R}."

    assert not _tem_variavel_de_template_adk(texto)
