from app.ai.prompts import prompt_resumo_estudo


def test_prompt_de_modulo_usa_o_conteudo_do_modulo_como_base():
    prompt = prompt_resumo_estudo(
        "História", "Idade Média", "Feudalismo", "Texto do módulo.", "aluno: o que é servo?"
    )

    assert "CONTEÚDO DO MÓDULO:\nTexto do módulo." in prompt
    assert "exclusivamente no CONTEÚDO do módulo" in prompt
    assert "<conversa_do_aluno>" in prompt


def test_prompt_de_conversa_livre_usa_a_conversa_como_unica_base():
    prompt = prompt_resumo_estudo(None, None, None, None, "aluno: o que é uma fração?")

    assert "aluno: o que é uma fração?" in prompt
    assert "única base do resumo" in prompt
    # sem conteúdo de módulo, nada pode mandar o modelo ignorar a conversa
    assert "CONTEÚDO DO MÓDULO" not in prompt
    assert "não na conversa" not in prompt


def test_prompt_nao_pede_fontes_ao_modelo():
    """As fontes vêm das páginas realmente citadas na pesquisa do tema; pedidas ao modelo,
    ele inventava rótulos como "Fontes 1" ... "Fontes 5"."""
    modulo = prompt_resumo_estudo("História", "Idade Média", "Feudalismo", "Texto.", None)
    livre = prompt_resumo_estudo(None, None, None, None, "aluno: oi")

    assert "'fontes'" not in modulo
    assert "'fontes'" not in livre
