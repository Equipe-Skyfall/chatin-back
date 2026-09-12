import uuid

import jwt


class JwtBuilder:
    """Builds signed test JWTs with overridable claims, for exercising
    `app.core.security` and auth-dependent routes without a real auth service.

    Matches the real auth service's token shape (authSys/src/infrastructure/
    services/TokenService.ts): claim is `userId` (a Prisma cuid() string, not
    a UUID - a random UUID string is used here as a stand-in id, since our
    side treats it as an opaque string either way), and `role` is `"ADMIN"`
    or `"USER"`.
    """

    def __init__(self, secret: str = "test-secret", algorithm: str = "HS256"):
        self._secret = secret
        self._algorithm = algorithm
        self._claims: dict = {"userId": str(uuid.uuid4())}

    def com_user_id(self, user_id: str) -> "JwtBuilder":
        self._claims["userId"] = user_id
        return self

    def como_admin(self) -> "JwtBuilder":
        self._claims["role"] = "ADMIN"
        return self

    def como_aluno(self) -> "JwtBuilder":
        self._claims["role"] = "USER"
        return self

    def sem_user_id(self) -> "JwtBuilder":
        self._claims.pop("userId", None)
        return self

    def build(self) -> str:
        return jwt.encode(self._claims, self._secret, algorithm=self._algorithm)
