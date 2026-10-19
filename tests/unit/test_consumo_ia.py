from types import SimpleNamespace

import pytest

from app.ai import consumo, resiliencia
from app.core.exceptions import ProvedorIAIndisponivelException


def _uso(entrada: int, saida: int):
    return SimpleNamespace(prompt_token_count=entrada, candidates_token_count=saida)


def test_registra_chamada_com_tokens_somados(consumo_registros):
    consumo.definir_usuario("u1")

    with consumo.medir("gerar_questionario"):
        consumo.acumular(_uso(10, 5), "gemini-x")
        consumo.acumular(_uso(3, 2))

    (registro,) = consumo_registros
    assert registro.operacao == "gerar_questionario"
    assert registro.user_id == "u1"
    assert registro.sucesso is True
    assert (registro.tokens_entrada, registro.tokens_saida) == (13, 7)
    assert registro.chamadas_modelo == 2
    assert registro.modelo == "gemini-x"
    consumo.definir_usuario(None)


def test_chamada_sem_uso_informado_fica_com_tokens_nulos(consumo_registros):
    with consumo.medir("x"):
        consumo.acumular(None)

    (registro,) = consumo_registros
    assert registro.tokens_entrada is None
    assert registro.chamadas_modelo == 1


def test_falha_e_registrada_e_a_excecao_segue(consumo_registros):
    with pytest.raises(ProvedorIAIndisponivelException):
        with consumo.medir("x"):
            raise ProvedorIAIndisponivelException("fora")

    (registro,) = consumo_registros
    assert registro.sucesso is False
    assert registro.tipo_falha == "indisponivel"


def test_gravador_quebrado_nunca_derruba_a_chamada():
    def quebrado(_registro):
        raise RuntimeError("banco fora do ar")

    consumo.definir_gravador(quebrado)

    with consumo.medir("x"):
        resultado = "resposta da IA"

    assert resultado == "resposta da IA"


def test_gravador_quebrado_nao_mascara_o_erro_original():
    consumo.definir_gravador(lambda _r: (_ for _ in ()).throw(RuntimeError("banco")))

    with pytest.raises(ProvedorIAIndisponivelException):
        with consumo.medir("x"):
            raise ProvedorIAIndisponivelException("fora")


def test_uso_com_formato_inesperado_e_ignorado(consumo_registros):
    with consumo.medir("x"):
        consumo.acumular(object())

    assert consumo_registros[0].tokens_saida is None


def test_cada_tentativa_do_retry_vira_um_registro(consumo_registros):
    chamadas = {"n": 0}

    @resiliencia.retry_transiente(tentativas=3, espera_max=0)
    def operacao_flaky():
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise ProvedorIAIndisponivelException("5xx")
        return "ok"

    assert operacao_flaky() == "ok"

    assert [r.sucesso for r in consumo_registros] == [False, False, True]
    assert {r.operacao for r in consumo_registros} == {"operacao_flaky"}


def test_tokens_somados_no_loop_em_outra_thread_chegam_na_medicao(consumo_registros):
    """O agente do chat roda num loop asyncio dedicado (`run_coroutine_threadsafe`);
    o contexto da medição precisa acompanhá-lo."""
    import asyncio
    import threading

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    async def corrotina():
        consumo.acumular(_uso(4, 2), "m")

    try:
        with consumo.medir("conversar_com_agente"):
            asyncio.run_coroutine_threadsafe(corrotina(), loop).result()
    finally:
        loop.call_soon_threadsafe(loop.stop)

    assert (consumo_registros[0].tokens_entrada, consumo_registros[0].tokens_saida) == (4, 2)
