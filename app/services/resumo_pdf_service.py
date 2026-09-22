"""Renders a `ResumoEstudo`'s structured template into a PDF, on demand (no
PDF bytes are stored anywhere). Uses `fpdf2` with its built-in core fonts -
pure-Python, so no system libraries are needed at deploy time.

Core fonts are latin-1 only, so `_sanitizar` folds the punctuation the model
commonly emits (em dashes, curly quotes, bullets, arrows) into latin-1-safe
equivalents before anything is written.
"""

from fpdf import FPDF

from app.models.resumo_estudo import ResumoEstudo

_SUBSTITUICOES = {
    "\u2014": "-",  # em dash
    "\u2013": "-",  # en dash
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u2022": "-",  # bullet
    "\u2192": "->",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2260": "!=",
    "\u00a0": " ",
}


def _sanitizar(texto: object) -> str:
    texto = str(texto)
    for origem, destino in _SUBSTITUICOES.items():
        texto = texto.replace(origem, destino)
    # Drop anything still outside latin-1 - fpdf's core fonts can't encode it.
    return texto.encode("latin-1", "replace").decode("latin-1")


def _escrever(pdf: FPDF, altura: float, texto: str) -> None:
    """`multi_cell` with an explicit cursor reset: without `new_x="LMARGIN"`
    the cursor stays at the right margin, and the next cell would have zero
    width. Centered on one place so every section behaves the same."""
    pdf.multi_cell(0, altura, _sanitizar(texto), new_x="LMARGIN", new_y="NEXT")


def _titulo(pdf: FPDF, texto: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 13)
    _escrever(pdf, 7, texto)


def _paragrafo(pdf: FPDF, texto: str) -> None:
    pdf.set_font("Helvetica", "", 11)
    _escrever(pdf, 6, texto)


def _itens(pdf: FPDF, itens: list) -> None:
    pdf.set_font("Helvetica", "", 11)
    for item in itens:
        _escrever(pdf, 6, f"- {item}")


def render_resumo_pdf(resumo: ResumoEstudo) -> bytes:
    conteudo = resumo.conteudo or {}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    _escrever(pdf, 9, resumo.titulo)

    cabecalho = " / ".join(
        p for p in (resumo.materia_nome, resumo.tema_titulo, resumo.modulo_titulo) if p
    )
    if cabecalho:
        pdf.set_font("Helvetica", "", 10)
        _escrever(pdf, 5, cabecalho)

    visao_geral = conteudo.get("visao_geral")
    if visao_geral:
        _titulo(pdf, "Visão geral")
        _paragrafo(pdf, visao_geral)

    conceitos = conteudo.get("conceitos_chave") or []
    if conceitos:
        _titulo(pdf, "Conceitos-chave")
        for conceito in conceitos:
            _paragrafo(pdf, f"{conceito.get('termo')}: {conceito.get('explicacao')}")

    duvidas = conteudo.get("duvidas_do_aluno") or []
    if duvidas:
        _titulo(pdf, "Dúvidas e respostas")
        for duvida in duvidas:
            _paragrafo(pdf, f"Pergunta: {duvida.get('pergunta')}")
            _paragrafo(pdf, f"Resposta: {duvida.get('resposta')}")

    for chave, rotulo in (
        ("pontos_importantes", "Pontos importantes"),
        ("exemplos", "Exemplos"),
        ("revisao_rapida", "Revisão rápida"),
        ("fontes", "Fontes"),
    ):
        itens = conteudo.get(chave) or []
        if itens:
            _titulo(pdf, rotulo)
            _itens(pdf, itens)

    return bytes(pdf.output())
