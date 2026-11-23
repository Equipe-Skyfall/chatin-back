from types import SimpleNamespace

from google.genai import types

from app.ai import janela_contexto


def _texto(role: str, texto: str):
    return types.Content(role=role, parts=[types.Part.from_text(text=texto)])


def _chamada(nome: str):
    return types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(name=nome, args={}))]
    )


def _resposta(nome: str):
    return types.Content(
        role="user",
        parts=[
            types.Part(function_response=types.FunctionResponse(name=nome, response={"ok": True}))
        ],
    )


def _conversa(turnos: int):
    contents = []
    for i in range(turnos):
        contents += [_texto("user", f"pergunta {i}"), _texto("model", f"resposta {i}")]
    return contents


def _textos(contents):
    return [c.parts[0].text for c in contents if c.parts[0].text]


def test_conversa_que_cabe_na_janela_segue_inteira():
    contents = _conversa(3)

    assert janela_contexto.recortar(contents, 20) == contents


def test_conversa_longa_manda_so_as_mensagens_recentes():
    contents = _conversa(50)  # 100 messages

    recorte = janela_contexto.recortar(contents, 20)

    assert len(recorte) == 20
    assert _textos(recorte)[0] == "pergunta 40"
    assert _textos(recorte)[-1] == "resposta 49"


def test_o_tamanho_enviado_para_de_crescer_com_a_conversa():
    tamanhos = {len(janela_contexto.recortar(_conversa(n), 12)) for n in (20, 80, 400)}

    assert tamanhos == {12}


def test_o_recorte_sempre_comeca_numa_mensagem_do_usuario():
    contents = _conversa(10)

    recorte = janela_contexto.recortar(contents, 5)  # 5 would open on a model reply

    assert recorte[0].role == "user"
    assert _textos(recorte)[0] == "pergunta 8"


def test_chamada_de_ferramenta_nao_e_separada_da_resposta():
    contents = [
        _texto("user", "p0"),
        _texto("model", "r0"),
        _texto("user", "p1"),
        _chamada("buscar"),
        _resposta("buscar"),
        _texto("model", "r1"),
        _texto("user", "p2"),
        _texto("model", "r2"),
    ]

    recorte = janela_contexto.recortar(contents, 3)

    nomes = [
        (p.function_call or p.function_response).name
        for c in recorte
        for p in c.parts
        if p.function_call or p.function_response
    ]
    assert nomes in ([], ["buscar", "buscar"])  # both halves or neither
    assert recorte[0].parts[0].text  # never opens on a bare tool response


def test_callback_recorta_o_pedido_ao_modelo_no_lugar():
    llm_request = SimpleNamespace(contents=_conversa(30))
    callback = janela_contexto.criar_callback(10)

    assert callback(SimpleNamespace(), llm_request) is None  # None = go on to the model
    assert len(llm_request.contents) == 10
