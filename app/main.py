from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.routers import chat, chat_aluno, materias, modulos, temas, tentativas, xp

configure_logging()
settings = get_settings()

app = FastAPI(title="ChatIn Study Service", version="0.1.0")

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(materias.router)
app.include_router(temas.router)
app.include_router(modulos.router)
app.include_router(tentativas.router)
app.include_router(chat.router)
app.include_router(chat_aluno.router)
app.include_router(xp.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
