from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.core.tracing import setup_tracing
from app.core.db import close_db
from app.core.redis_client import close_redis
from app.core.qdrant_client import close_qdrant, ensure_collections
from app.api.v1 import chat, documents, evals, health, traces
from app.models.common import ErrorResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("app_starting", env=settings.app_env, debug=settings.app_debug)

    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    await ensure_collections()
    logger.info("app_started")

    yield

    await close_db()
    await close_redis()
    await close_qdrant()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title="智能投研助手 Agent",
        version="0.1.0",
        description="Investment Research Intelligent Agent Platform",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    setup_tracing(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(traces.router, prefix="/api/v1")
    app.include_router(evals.router, prefix="/api/v1")

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="An unexpected error occurred",
            ).model_dump(),
        )

    return app


app = create_app()
