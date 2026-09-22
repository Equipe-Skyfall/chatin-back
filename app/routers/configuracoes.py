from fastapi import APIRouter

from app.deps import AdminUserId, ConfiguracaoRepo
from app.models.configuracao import ConfiguracaoSistema
from app.schemas.configuracao import ConfiguracaoOut, ConfiguracaoUpdate

router = APIRouter(tags=["configuracoes"])


def _out(config: ConfiguracaoSistema) -> ConfiguracaoOut:
    return ConfiguracaoOut(xp_penalidade_reprovacao=config.xp_penalidade_reprovacao)


@router.get("/admin/configuracoes", response_model=ConfiguracaoOut)
def obter_configuracoes(admin_id: AdminUserId, config_repo: ConfiguracaoRepo) -> ConfiguracaoOut:
    return _out(config_repo.obter())


@router.put("/admin/configuracoes", response_model=ConfiguracaoOut)
def atualizar_configuracoes(
    body: ConfiguracaoUpdate, admin_id: AdminUserId, config_repo: ConfiguracaoRepo
) -> ConfiguracaoOut:
    return _out(config_repo.definir_penalidade(body.xp_penalidade_reprovacao))
