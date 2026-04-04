"""
Health check utilities for all platform services.

Provides async checks for database, Redis, model availability,
and overall system readiness. Used by the /health endpoint and
liveness/readiness probes in container orchestration.
"""

import asyncio
import time
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


async def check_database(database_url: str) -> Dict[str, Any]:
    """Check PostgreSQL connectivity and response time."""
    start = time.monotonic()
    try:
        import asyncpg
        conn = await asyncpg.connect(
            database_url.replace("postgresql+asyncpg://", "postgresql://"),
            timeout=5,
        )
        await conn.fetchval("SELECT 1")
        await conn.close()
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }


async def check_redis(redis_url: str) -> Dict[str, Any]:
    """Check Redis connectivity and response time."""
    start = time.monotonic()
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, socket_connect_timeout=5)
        await client.ping()
        await client.aclose()
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }


def check_model_files(model_path: str, easyocr_path: str) -> Dict[str, Any]:
    """Verify that required ML model files are present on disk."""
    results: Dict[str, Any] = {}

    yolo_ok = os.path.isfile(model_path)
    results["yolo"] = {
        "path": model_path,
        "status": "ok" if yolo_ok else "missing",
    }

    easyocr_ok = os.path.isdir(easyocr_path) and bool(os.listdir(easyocr_path))
    results["easyocr"] = {
        "path": easyocr_path,
        "status": "ok" if easyocr_ok else "missing",
    }

    results["status"] = "ok" if (yolo_ok and easyocr_ok) else "degraded"
    return results


async def run_all_checks(settings) -> Dict[str, Any]:
    """
    Run all health checks concurrently and return a summary.

    Args:
        settings: Application Settings instance from config.py

    Returns:
        Dict with per-service status and an overall 'healthy' flag.
    """
    db_task = asyncio.create_task(check_database(settings.get_database_url()))
    redis_task = asyncio.create_task(check_redis(settings.get_redis_url()))

    db_result, redis_result = await asyncio.gather(db_task, redis_task)
    model_result = check_model_files(settings.model_path, settings.easyocr_model_path)

    healthy = all(
        r.get("status") == "ok"
        for r in [db_result, redis_result, model_result]
    )

    return {
        "healthy": healthy,
        "services": {
            "database": db_result,
            "redis": redis_result,
            "models": model_result,
        },
    }
