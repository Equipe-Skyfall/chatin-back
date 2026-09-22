import uuid

from app.models.resumo_estudo import ResumoEstudo
from app.services import resumo_pdf_service


def _resumo(conteudo: dict) -> ResumoEstudo:
    return ResumoEstudo(
        id=uuid.uuid4(),
        user_id="user-1",
        modulo_id=uuid.uuid4(),
        titulo="Limites",
        materia_nome="Matemática",
        tema_titulo="Cálculo 1",
        modulo_titulo="Limites",
        conteudo=conteudo,
        modelo_ia="fake-model",
    )


def test_render_gera_pdf_valido():
    resumo = _resumo(
        {
            "visao_geral": "Visão geral do módulo.",
            "conceitos_chave": [{"termo": "Limite", "explicacao": "Tendência de uma função."}],
            "pontos_importantes": ["Limite lateral é diferente de limite."],
            "exemplos": ["lim x->0 de 1/x"],
            "duvidas_do_aluno": [{"pergunta": "O que é limite?", "resposta": "Uma tendência."}],
            "revisao_rapida": ["Revisar limites laterais."],
            "fontes": ["https://example.org"],
        }
    )

    pdf = resumo_pdf_service.render_resumo_pdf(resumo)

    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_render_nao_quebra_com_caracteres_fora_de_latin1():
    # Em dashes, curly quotes and bullets are outside latin-1 - the sanitizer
    # must fold them instead of letting fpdf's core font raise.
    resumo = _resumo(
        {
            "visao_geral": "Texto com travessão — e aspas “curvas”… e bullet • aqui.",
            "conceitos_chave": [],
            "pontos_importantes": ["Símbolos: → ≤ ≥ ≠"],
            "exemplos": [],
            "duvidas_do_aluno": [],
            "revisao_rapida": [],
            "fontes": [],
        }
    )

    pdf = resumo_pdf_service.render_resumo_pdf(resumo)

    assert pdf.startswith(b"%PDF")
