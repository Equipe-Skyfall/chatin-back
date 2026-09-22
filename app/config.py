from functools import lru_cache
from typing import Literal

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

    # AI provider (strategy selection) - "adk" (the default) runs
    # gerar_questionario/planejar_modulos/gerar_conteudo_modulo/buscar_fontes/
    # conversar_com_ferramentas through Google ADK (output_schema validation,
    # and, for the admin chat, a persistent ADK SessionService that keeps
    # full tool-call granularity - see AdkProvider.obter_historico_sessao).
    # "gemini" is kept as an instant rollback to the legacy GeminiProvider
    # path, but note that agent_service no longer persists per-tool-call
    # messages itself, so the admin chat's tool-call history is unavailable
    # under "gemini" specifically.
    AI_PROVIDER: Literal["gemini", "adk"] = "adk"
    GEMINI_API_KEY: str
    GEMINI_MODEL_CONTEUDO: str = "gemini-2.5-flash"
    GEMINI_MODEL_QUESTIONARIO: str = "gemini-2.5-flash"
    GEMINI_MODEL_SEARCH: str = "gemini-2.5-flash"
    GEMINI_MODEL_AGENTE: str = "gemini-2.5-flash"
    GEMINI_MODEL_PROFESSOR: str = "gemini-2.5-flash"

    # Content generation tuning
    QUESTIONARIO_POOL_SIZE: int = 12
    TENTATIVA_NUM_QUESTOES: int = 5
    PONTUACAO_MINIMA_APROVACAO: float = 75.0
    AGENTE_MAX_ITERACOES: int = 8  # safety cap on tool-call round-trips per chat turn

    # Student chat: how many of a conversation's most recent messages are sent
    # to the model each turn - bounds prompt size (and cost) on long chats.
    MEMORIA_JANELA_MENSAGENS: int = 20

    # App
    ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def adk_session_db_url(self) -> str:
        """`SUPABASE_DB_URL` with its driver swapped for an async one -
        the ADK's `DatabaseSessionService` (used by `AdkProvider` for the
        admin agent's conversation history) requires an async SQLAlchemy
        engine, while every other repository in this app stays on the
        synchronous `psycopg` engine. This is the one place that engine
        needs to exist, isolated from the rest of the app."""
        scheme, rest = self.SUPABASE_DB_URL.split("://", 1)
        backend = scheme.split("+", 1)[0]
        return f"{backend}+asyncpg://{rest}"


@lru_cache
def get_settings() -> Settings:
    """Singleton: Settings is constructed once and reused for the app's lifetime."""
    return Settings()
