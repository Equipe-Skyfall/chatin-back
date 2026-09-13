from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase / Postgres
    SUPABASE_DB_URL: str
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    # AI provider (strategy selection)
    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str
    GEMINI_MODEL_CONTEUDO: str = "gemini-2.5-flash"
    GEMINI_MODEL_QUESTIONARIO: str = "gemini-2.5-flash"
    GEMINI_MODEL_SEARCH: str = "gemini-2.5-flash"
    GEMINI_MODEL_AGENTE: str = "gemini-2.5-flash"
    GEMINI_MODEL_PROFESSOR: str = "gemini-2.5-flash"

    # Content generation tuning
    QUESTIONARIO_POOL_SIZE: int = 12
    TENTATIVA_NUM_QUESTOES: int = 5
    PONTUACAO_MINIMA_APROVACAO: float = 60.0
    AGENTE_MAX_ITERACOES: int = 8  # safety cap on tool-call round-trips per chat turn
    TRILHAS_MAX_POR_USUARIO: int = 3  # cap on personal (non-admin) matérias per student

    # App
    ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton: Settings is constructed once and reused for the app's lifetime."""
    return Settings()
