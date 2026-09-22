"""Central place where FastAPI dependencies are wired up. Each repository
defines its own provider function *and* its own `Annotated` alias at the
bottom of its module, next to the class it builds (e.g. `MateriaRepo` lives in
`materia_repository.py`). This file re-exports them - alongside the
auth/AI-provider wiring that doesn't belong to any single repository - so
routers still only need one import line: `from app.deps import ...`.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ai.adk_provider import AdkProvider
from app.ai.base import AIProvider
from app.ai.gemini_provider import GeminiProvider
from app.config import Settings, get_settings
from app.core.exceptions import NaoAutenticadoException
from app.core.security import TokenPayload, decode_token, require_admin_role
from app.repositories.conversa_repository import ConversaRepo
from app.repositories.materia_repository import MateriaRepo
from app.repositories.modulo_repository import ModuloRepo
from app.repositories.perfil_repository import PerfilRepo
from app.repositories.progresso_repository import ProgressoRepo
from app.repositories.questionario_repository import QuestionarioRepo
from app.repositories.resumo_estudo_repository import ResumoEstudoRepo
from app.repositories.tema_repository import TemaRepo
from app.repositories.tentativa_repository import TentativaRepo
from app.repositories.voto_repository import VotoRepo
from app.repositories.xp_repository import XpRepo

__all__ = [
    "SettingsDep",
    "TokenPayloadDep",
    "CurrentUserId",
    "AdminUserId",
    "AiProviderDep",
    "MateriaRepo",
    "TemaRepo",
    "ModuloRepo",
    "QuestionarioRepo",
    "TentativaRepo",
    "ProgressoRepo",
    "ConversaRepo",
    "XpRepo",
    "PerfilRepo",
    "VotoRepo",
    "ResumoEstudoRepo",
]

SettingsDep = Annotated[Settings, Depends(get_settings)]

# A proper `HTTPBearer` security scheme (rather than reading a raw `Header`)
# is what makes FastAPI register a real OpenAPI security scheme - which is
# what gives Swagger UI (`/docs`) its single "Authorize" padlock button
# instead of a per-endpoint free-text header field. `auto_error=False` so a
# missing header raises our own `NaoAutenticadoException`, not FastAPI's.
_bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def get_token_payload(settings: SettingsDep, credentials: BearerCredentials) -> TokenPayload:
    if credentials is None:
        raise NaoAutenticadoException("Cabeçalho Authorization ausente ou inválido.")
    return decode_token(credentials.credentials, settings)


TokenPayloadDep = Annotated[TokenPayload, Depends(get_token_payload)]


def _sincronizar_perfil(payload: TokenPayload, perfil_repo: PerfilRepo) -> None:
    """Opportunistic write-through: this service has no other access to
    authSys's user data, so every authenticated request refreshes the local
    `perfis_usuario` mirror from that request's own JWT claims - see
    `PerfilRepository.upsert` for why this is cheap enough to run on every
    request rather than needing a separate sync job."""
    if payload.username or payload.email:
        perfil_repo.upsert(payload.user_id, payload.username, payload.email)


def get_current_user_id(payload: TokenPayloadDep, perfil_repo: PerfilRepo) -> str:
    _sincronizar_perfil(payload, perfil_repo)
    return payload.user_id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]


def require_admin(payload: TokenPayloadDep, perfil_repo: PerfilRepo) -> str:
    require_admin_role(payload)
    _sincronizar_perfil(payload, perfil_repo)
    return payload.user_id


AdminUserId = Annotated[str, Depends(require_admin)]


@lru_cache
def get_ai_provider() -> AIProvider:
    """Strategy selection, folded in here rather than a separate factory file -
    there's a single provider and a single selection rule (AI_PROVIDER) today.
    Cached so exactly one instance is built and reused (singleton). Takes no
    FastAPI-resolved parameters on purpose, so it's safe to use as a
    dependency without it being mistaken for a request param.
    """
    settings = get_settings()
    if settings.AI_PROVIDER == "adk":
        return AdkProvider(settings)
    if settings.AI_PROVIDER == "gemini":
        return GeminiProvider(settings)
    raise ValueError(f"Provedor de IA desconhecido: {settings.AI_PROVIDER}")


AiProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]
