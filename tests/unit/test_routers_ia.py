from fastapi.testclient import TestClient

from app.ai.disponibilidade import FALHAS_SEGUIDAS, status_ia
from app.main import app

client = TestClient(app)


def test_status_disponivel_por_padrao_e_sem_autenticacao():
    resposta = client.get("/ia/status")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "disponivel": True,
        "tentar_novamente_em_segundos": 0,
        "recursos_afetados": [],
    }


def test_status_indisponivel_lista_o_que_para_de_funcionar():
    for _ in range(FALHAS_SEGUIDAS):
        status_ia.registrar_falha()

    corpo = client.get("/ia/status").json()

    assert corpo["disponivel"] is False
    assert 0 < corpo["tentar_novamente_em_segundos"] <= 60
    assert "chat" in corpo["recursos_afetados"]
    assert "questionario_personalizado" in corpo["recursos_afetados"]
    # what must keep working is never listed as affected
    assert not {"quiz", "conteudo", "progresso"} & set(corpo["recursos_afetados"])
