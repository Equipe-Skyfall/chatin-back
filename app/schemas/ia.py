from pydantic import BaseModel


class IAStatusOut(BaseModel):
    disponivel: bool
    # Seconds until the next call is allowed to find out whether the provider
    # is back; 0 when `disponivel`.
    tentar_novamente_em_segundos: int
    # Features that stop working while the provider is down, so the frontend
    # knows what to disable. Everything else keeps working.
    recursos_afetados: list[str]


class ConsumoItemOut(BaseModel):
    # `operacao` for the per-operation breakdown, `user_id` for the per-user one.
    chave: str
    chamadas: int
    falhas: int
    tokens_entrada: int
    tokens_saida: int


class IAConsumoOut(BaseModel):
    """AI usage in the last `periodo_dias` days (RNF7). Tokens only count calls
    where the provider reported usage, so they are a lower bound."""

    periodo_dias: int
    chamadas: int
    falhas: int
    tokens_entrada: int
    tokens_saida: int
    por_operacao: list[ConsumoItemOut]
    por_usuario: list[ConsumoItemOut]
