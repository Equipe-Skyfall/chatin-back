from app.ai import resiliencia
from app.config import Settings


def _settings(**extra) -> Settings:
    return Settings(
        SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
        JWT_SECRET="test-secret",
        GEMINI_API_KEY="fake-key",
        **extra,
    )


def test_timeout_http_vem_da_config_em_milissegundos():
    opcoes = resiliencia.opcoes_http(_settings(GEMINI_TIMEOUT_SECONDS=12.5))

    assert opcoes.timeout == 12500


def test_timeout_padrao_e_de_60_segundos():
    assert resiliencia.opcoes_http(_settings()).timeout == 60000
