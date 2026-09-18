import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.db.session import engine
from app.services.broadcast_service import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

CHECK_TIMEOUT_SECONDS = 2


def _ping_database():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


async def _check(name: str, probe) -> str:
    try:
        await asyncio.wait_for(probe(), timeout=CHECK_TIMEOUT_SECONDS)
        return "ok"
    except Exception:
        # Details go to the logs, not to an unauthenticated endpoint
        logger.exception("Health check failed: %s", name)
        return "unavailable"


@router.get("/health")
async def health():
    """
    Liveness and dependency check for the load balancer / Render.

    Returns 503 if Postgres or Redis is unreachable, so an instance that can't
    serve requests (or deliver real-time events) is taken out of rotation.
    """
    database, redis = await asyncio.gather(
        _check("database", lambda: run_in_threadpool(_ping_database)),
        _check("redis", redis_client.ping),
    )
    healthy = database == "ok" and redis == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "database": database, "redis": redis},
    )
