from pydantic import BaseModel


class IAStatusOut(BaseModel):
    disponivel: bool
    # Seconds until the next call is allowed to find out whether the provider
    # is back; 0 when `disponivel`.
    tentar_novamente_em_segundos: int
    # Features that stop working while the provider is down, so the frontend
    # knows what to disable. Everything else keeps working.
    recursos_afetados: list[str]
