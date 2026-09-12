"""JWT verification for tokens issued by the external user/auth microservice
(the Node/Prisma service at authSys/).

This service does not issue tokens - it only validates them. Uses a shared
HS256 secret for now (JWT_SECRET). If/when the auth service moves to RS256 +
JWKS, only `decode_token` needs to change (e.g. to `PyJWKClient`) - callers
(`app.deps.get_current_user_id` / `require_admin`) keep the same contract.

The auth service's `TokenService.generateToken` (see authSys/src/infrastructure/
services/TokenService.ts) signs `{ userId, email, username, role }` - note
`userId`, not the more common `sub` claim - where `userId` is a Prisma
`cuid()` string (e.g. "cl9ebqhxk00003b600tymydho"), NOT a UUID. `role` is
`"ADMIN"` or `"USER"` (see authSys/prisma/schema.prisma's `Role` enum).
"""

from dataclasses import dataclass

import jwt

from app.config import Settings
from app.core.exceptions import AcessoNegadoException, NaoAutenticadoException

ADMIN_ROLE = "ADMIN"

# authSys runs on its own host (Vercel) with its own clock; a token's `iat` can
# land a fraction of a second ahead of this service's clock purely from normal
# drift between machines, which PyJWT otherwise rejects with zero tolerance.
CLOCK_SKEW_LEEWAY_SECONDS = 30


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    role: str | None


def decode_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
        )
    except jwt.PyJWTError as exc:
        raise NaoAutenticadoException("Token inválido ou expirado.") from exc

    user_id = payload.get("userId")
    if not user_id:
        raise NaoAutenticadoException("Token não contém identificador de usuário (userId).")

    return TokenPayload(user_id=str(user_id), role=payload.get("role"))


def require_admin_role(payload: TokenPayload) -> None:
    if payload.role != ADMIN_ROLE:
        raise AcessoNegadoException("Esta ação requer privilégios de administrador.")
