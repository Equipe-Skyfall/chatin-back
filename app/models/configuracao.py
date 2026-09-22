from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CONFIGURACAO_ID = 1


class ConfiguracaoSistema(Base):
    """Parâmetros do sistema editáveis pelo admin em runtime - hoje só o
    desconto de XP por reprovar no questionário final de um módulo.

    Single-row (`id = 1`): é um conjunto único de parâmetros, não uma coleção.
    O que não estiver aqui continua vindo de `Settings` (env).
    """

    __tablename__ = "configuracoes_sistema"
    __table_args__ = (CheckConstraint("id = 1", name="ck_configuracoes_sistema_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=CONFIGURACAO_ID)
    xp_penalidade_reprovacao: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
