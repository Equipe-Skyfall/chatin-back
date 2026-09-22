import uuid

from app.core.exceptions import ProvedorIAIndisponivelException
from app.schemas.tentativa import RespostaResultadoOut
from app.services import feedback_tentativa_service


def _resultado(correta: bool, enunciado: str = "Questão de teste") -> RespostaResultadoOut:
    return RespostaResultadoOut(
        questao_id=uuid.uuid4(),
        enunciado=enunciado,
        resposta_escolhida="A",
        resposta_correta="B",
        correta=correta,
        explicacao="Explicação de teste.",
    )


def test_sem_erros_nao_chama_a_ia(fake_ai_provider):
    feedback = feedback_tentativa_service.gerar_feedback([_resultado(True)], fake_ai_provider)

    assert feedback is None
    assert fake_ai_provider.gerar_feedback_erros_calls == 0


def test_com_erros_chama_a_ia_apenas_com_os_errados(fake_ai_provider):
    feedback = feedback_tentativa_service.gerar_feedback(
        [_resultado(True), _resultado(False), _resultado(False)], fake_ai_provider
    )

    assert feedback == "Feedback de teste."
    assert fake_ai_provider.gerar_feedback_erros_calls == 1
    assert len(fake_ai_provider.erros_recebidos[0]) == 2


def test_falha_da_ia_degrada_para_none(fake_ai_provider, monkeypatch):
    def _falhar(_erros):
        raise ProvedorIAIndisponivelException("provedor fora do ar")

    monkeypatch.setattr(fake_ai_provider, "gerar_feedback_erros", _falhar)

    # Não pode propagar: a correção da tentativa já aconteceu e não pode
    # ser desfeita por causa do feedback (RNF6).
    assert feedback_tentativa_service.gerar_feedback([_resultado(False)], fake_ai_provider) is None
