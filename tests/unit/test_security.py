import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import Settings
from app.core.exceptions import AcessoNegadoException, NaoAutenticadoException
from app.core.security import decode_token, require_admin_role
from tests.builders.jwt_builder import JwtBuilder

SECRET = "test-secret"


def _settings() -> Settings:
    return Settings(
        SUPABASE_DB_URL="postgresql+psycopg://user:pass@localhost:5432/db",
        JWT_SECRET=SECRET,
        GEMINI_API_KEY="fake-key",
    )


def test_decode_token_valido_retorna_user_id_e_role():
    user_id = str(uuid.uuid4())
    token = JwtBuilder(secret=SECRET).com_user_id(user_id).como_admin().build()

    payload = decode_token(token, _settings())

    assert payload.user_id == user_id
    assert payload.role == "ADMIN"


def test_decode_token_expirado_levanta_excecao():
    token = jwt.encode(
        {"userId": str(uuid.uuid4()), "exp": datetime.now(UTC) - timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(NaoAutenticadoException):
        decode_token(token, _settings())


def test_decode_token_assinatura_invalida_levanta_excecao():
    token = JwtBuilder(secret="outro-secret").build()

    with pytest.raises(NaoAutenticadoException):
        decode_token(token, _settings())


def test_decode_token_sem_user_id_levanta_excecao():
    token = JwtBuilder(secret=SECRET).sem_user_id().build()

    with pytest.raises(NaoAutenticadoException):
        decode_token(token, _settings())


def test_require_admin_role_aceita_admin():
    token = JwtBuilder(secret=SECRET).como_admin().build()
    payload = decode_token(token, _settings())
    require_admin_role(payload)  # should not raise


def test_require_admin_role_rejeita_aluno():
    token = JwtBuilder(secret=SECRET).como_aluno().build()
    payload = decode_token(token, _settings())
    with pytest.raises(AcessoNegadoException):
        require_admin_role(payload)
