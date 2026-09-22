from pydantic import BaseModel, Field


class ConfiguracaoOut(BaseModel):
    xp_penalidade_reprovacao: int


class ConfiguracaoUpdate(BaseModel):
    xp_penalidade_reprovacao: int = Field(..., ge=0)
