import logging
from fastapi.middleware.cors import CORSMiddleware

import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import get_settings
from app.routes.export_routes import router as export_router
from app.routes.db_routes import router as db_router

def configure_logging() -> None:
    """Configures application-wide logging format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for initialization and cleanup."""
    configure_logging()
    settings = get_settings()
    logger = logging.getLogger("arrt_extractor")
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"ARRT Target URL: {settings.arrt_api_url}")
    logger.info(f"Exports Directory: {settings.exports_dir.resolve()}")
    logger.info(f"Max Concurrency: {settings.max_concurrency}")

    if not settings.is_auth_configured():
        logger.warning(
            "ARRT credentials (ARRT_CAPTCHA_TOKEN) not set. Live requests may fail without valid session tokens."
        )

    yield

    logger.info(f"Shutting down {settings.app_name}")

def create_app() -> FastAPI:
    """Factory creating and configuring the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Asynchronous backend extractor that queries the external ARRT verification directory "
            "with partitioned first-name wildcards and exports unique records to CSV."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS configuration – allow UI (http://localhost:5173) during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # For production replace with your UI URL list
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(export_router)
    app.include_router(db_router)
    return app

app = create_app()
