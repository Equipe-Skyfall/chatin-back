import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.exception("Unhandled AppException on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything that isn't an `AppException` (a raw DB error, a bug,
    etc.). Without this, Starlette's own default handler returns the 500
    *outside* CORSMiddleware, so the response is missing CORS headers and the
    browser reports it to JS as an opaque network failure ("Failed to fetch")
    instead of a readable error - this handler runs inside the normal
    middleware stack, so CORS headers still get attached.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
