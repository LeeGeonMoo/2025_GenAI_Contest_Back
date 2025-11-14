from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.db.mongo import close_db, init_db


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    application = FastAPI(
        title=settings.project_name,
        version="0.1.0",
    )

    # CORS 설정
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite 개발 서버
            "http://localhost:3000",  # React 개발 서버 (필요시)
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router, prefix="/api")

    @application.on_event("startup")
    async def _startup() -> None:
        await init_db()
        await start_scheduler()

    @application.on_event("shutdown")
    async def _shutdown() -> None:
        await close_db()
        await shutdown_scheduler()

    return application


app = create_app()
