"""
FastAPI application entry point for Multimodal Traffic Intelligence Platform.

Configures the application with middleware, routers, error handlers,
and lifecycle management with proper async initialization.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import settings
from database.connection import AsyncSessionFactory
from database import queries as db_queries
from database.models import Base
from models.detection import load_model, get_model
from models.ocr import load_ocr_model
from utils.redis_client import init_redis
from api.routes import router as api_router
from api.websocket_routes import router as ws_router

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Global state for database and model initialization
class AppState:
    """Application state container."""

    db_factory: AsyncSessionFactory | None = None
    redis = None
    detection_model = None
    ocr_model = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan context manager.

    Handles startup and shutdown events:
        - Initialize database connection factory
        - Load ML models (YOLOv8, OCR)
        - Setup Redis cache
        - Cleanup resources on shutdown

    Args:
        app: FastAPI application instance

    Yields:
        During app startup/shutdown
    """
    # Startup
    try:
        logger.info("Starting Multimodal Traffic Intelligence Platform")

        # Initialize database factory
        try:
            logger.info("Initializing database connection factory...")
            app_state.db_factory = AsyncSessionFactory(
                database_url=settings.database_url,
                echo=settings.debug,
                pool_size=20,
                max_overflow=10,
            )
            db_queries.init_db(app_state.db_factory)
            # Create all tables if they don't exist
            async with app_state.db_factory.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database factory initialized and tables created successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

        # Initialize Redis
        try:
            logger.info("Initializing Redis cache...")
            app_state.redis = await init_redis(settings.redis_url)
            logger.info("Redis initialized successfully")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}. Continuing without cache.")

        # Load detection model
        try:
            logger.info("Loading YOLOv8 detection model...")
            app_state.detection_model = load_model(settings.model_path)
            logger.info("Detection model loaded successfully")
        except Exception as e:
            logger.warning(f"Detection model loading failed: {e}. Detection features will be unavailable.")

        # Load OCR model
        try:
            logger.info("Loading EasyOCR model...")
            app_state.ocr_model = load_ocr_model()
            logger.info("OCR model loaded successfully")
        except Exception as e:
            logger.warning(f"OCR model loading failed: {e}. OCR features disabled.")

        logger.info("All components initialized successfully")

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    # Yield to app
    yield

    # Shutdown
    try:
        logger.info("Shutting down Multimodal Traffic Intelligence Platform")

        # Close database connections
        if app_state.db_factory:
            try:
                await app_state.db_factory.dispose()
                logger.info("Database connections closed")
            except Exception as e:
                logger.error(f"Database shutdown error: {e}")

        # Close Redis connections
        if app_state.redis:
            try:
                await app_state.redis.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Redis shutdown error: {e}")

        logger.info("Shutdown completed")

    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Real-time multimodal traffic intelligence and analysis platform",
    version=settings.api_version,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    lifespan=lifespan,
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(api_router)
app.include_router(ws_router)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with detailed information."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with logging."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Root endpoints
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.api_version,
        "status": "running",
        "docs_url": f"{settings.api_prefix}/docs",
        "redoc_url": f"{settings.api_prefix}/redoc",
    }


@app.get(f"{settings.api_prefix}/health", tags=["system"])
async def health_check():
    """Health endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "version": settings.api_version,
    }


# Static files
try:
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        logger.info(f"Static files mounted from {static_dir}")
except Exception as e:
    logger.debug(f"Static files not mounted: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
