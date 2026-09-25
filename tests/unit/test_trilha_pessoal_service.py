import uuid
from datetime import UTC, datetime, timedelta

from app.models.modulo import STATUS_ERRO as MODULO_ERRO
from app.models.modulo import STATUS_GERANDO as MODULO_GERANDO
from app.models.modulo import STATUS_PRONTO as MODULO_PRONTO
from app.models.modulo import Modulo
from app.models.tema import STATUS_ERRO as TEMA_ERRO
from app.models.tema import STATUS_GERANDO as TEMA_GERANDO
from app.models.tema import STATUS_PRONTO as TEMA_PRONTO
from app.models.tema import Tema
from app.services.trilha_pessoal_service import (
    TIMEOUT_GERACAO,
    calcular_status_tema,
    reabrir_modulos_travados,
    reabrir_temas_travados,
)


def _tema(status: str) -> Tema:
    return Tema(id=uuid.uuid4(), materia_id=uuid.uuid4(), titulo="T", status=status)


def _modulo(status: str) -> Modulo:
    return Modulo(id=uuid.uuid4(), tema_id=uuid.uuid4(), titulo="M", status=status)


# --- calcular_status_tema ---


def test_tema_ainda_buscando_fontes_nao_esta_pronto():
    status = calcular_status_tema(_tema(TEMA_GERANDO), [])
    assert status["pronto_para_estudar"] is False
    assert status["tema_status"] == TEMA_GERANDO


def test_tema_pronto_sem_modulos_ainda_nao_esta_pronto_para_estudar():
    """Sources found but the split hasn't produced anything yet (or hasn't
    started) - not ready, even though `tema.status == 'pronto'`. This is
    exactly the gap that motivated this function existing."""
    status = calcular_status_tema(_tema(TEMA_PRONTO), [])
    assert status["modulos_total"] == 0
    assert status["pronto_para_estudar"] is False


def test_tema_pronto_com_modulo_ainda_gerando_nao_esta_pronto():
    status = calcular_status_tema(_tema(TEMA_PRONTO), [_modulo(MODULO_GERANDO)])
    assert status["pronto_para_estudar"] is False


def test_tema_pronto_com_todos_modulos_prontos_esta_pronto_para_estudar():
    modulos = [_modulo(MODULO_PRONTO), _modulo(MODULO_PRONTO)]
    status = calcular_status_tema(_tema(TEMA_PRONTO), modulos)
    assert status["modulos_total"] == 2
    assert status["modulos_prontos"] == 2
    assert status["pronto_para_estudar"] is True


def test_split_parcial_ainda_conta_como_pronto_para_estudar():
    """Some módulos failed, some succeeded - a partially-generated trilha is
    still usable, not a total failure (curriculo_service.dividir_tema_em_
    modulos already tolerates this per-módulo)."""
    modulos = [_modulo(MODULO_PRONTO), _modulo(MODULO_ERRO)]
    status = calcular_status_tema(_tema(TEMA_PRONTO), modulos)
    assert status["modulos_prontos"] == 1
    assert status["modulos_com_erro"] == 1
    assert status["pronto_para_estudar"] is True


def test_tema_erro_nunca_esta_pronto_mesmo_com_modulos():
    status = calcular_status_tema(_tema(TEMA_ERRO), [_modulo(MODULO_PRONTO)])
    assert status["pronto_para_estudar"] is False


# --- reabrir_temas_travados / reabrir_modulos_travados ---


class _FakeTravadoRepo:
    def __init__(self, itens, status_attr="status"):
        self._itens = itens
        self._status_attr = status_attr
        self.commits = 0

    def list_travados_desde(self, status, limite):
        return [
            i
            for i in self._itens
            if getattr(i, self._status_attr) == status and i.updated_at < limite
        ]

    def atualizar_status(self, item, status):
        setattr(item, self._status_attr, status)

    def commit(self):
        self.commits += 1


def _com_updated_at(entidade, quando: datetime):
    entidade.updated_at = quando
    return entidade


def test_tema_travado_ha_muito_tempo_vira_erro():
    limite = datetime.now(UTC) - TIMEOUT_GERACAO - timedelta(minutes=1)
    antigo = _com_updated_at(_tema(TEMA_GERANDO), limite)
    repo = _FakeTravadoRepo([antigo])

    reabrir_temas_travados(repo)

    assert antigo.status == TEMA_ERRO
    assert repo.commits == 1


def test_tema_gerando_recente_nao_e_mexido():
    recente = _com_updated_at(_tema(TEMA_GERANDO), datetime.now(UTC))
    repo = _FakeTravadoRepo([recente])

    reabrir_temas_travados(repo)

    assert recente.status == TEMA_GERANDO


def test_modulo_travado_ha_muito_tempo_vira_erro():
    limite = datetime.now(UTC) - TIMEOUT_GERACAO - timedelta(minutes=1)
    antigo = _com_updated_at(_modulo(MODULO_GERANDO), limite)
    repo = _FakeTravadoRepo([antigo])

    reabrir_modulos_travados(repo)

    assert antigo.status == MODULO_ERRO
