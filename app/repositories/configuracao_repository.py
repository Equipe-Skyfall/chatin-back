from typing import Annotated

from fastapi import Depends

from app.db.session import DbSession
from app.models.configuracao import CONFIGURACAO_ID, ConfiguracaoSistema
from app.repositories.base import SqlAlchemyRepository


class ConfiguracaoRepository(SqlAlchemyRepository[ConfiguracaoSistema]):
    model = ConfiguracaoSistema

    def obter(self) -> ConfiguracaoSistema:
        """Always returns the singleton row, creating it from the model's
        defaults the first time it's needed (e.g. before any migration-seeded
        row exists) - so callers never have to handle a missing config."""
        config = self.db.get(self.model, CONFIGURACAO_ID)
        if config is None:
            config = ConfiguracaoSistema(id=CONFIGURACAO_ID)
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def definir_penalidade(self, penalidade: int) -> ConfiguracaoSistema:
        config = self.obter()
        config.xp_penalidade_reprovacao = penalidade
        self.db.commit()
        self.db.refresh(config)
        return config


def get_configuracao_repository(db: DbSession) -> ConfiguracaoRepository:
    return ConfiguracaoRepository(db)


ConfiguracaoRepo = Annotated[ConfiguracaoRepository, Depends(get_configuracao_repository)]
