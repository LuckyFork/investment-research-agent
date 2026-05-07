import asyncio
from fastapi import APIRouter
from app.core.db import check_db_connection
from app.core.redis_client import check_redis_connection
from app.core.qdrant_client import check_qdrant_connection
from app.models.common import BaseResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ping", response_model=BaseResponse[str])
async def ping():
    return BaseResponse(data="pong")


@router.get("/ready", response_model=BaseResponse[dict])
async def readiness():
    """检查所有依赖服务连通性，用于 K8s readiness probe."""
    db_ok, redis_ok, qdrant_ok = await asyncio.gather(
        check_db_connection(),
        check_redis_connection(),
        check_qdrant_connection(),
    )

    services = {
        "postgres": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "qdrant": "ok" if qdrant_ok else "error",
    }
    all_ok = all(v == "ok" for v in services.values())

    return BaseResponse(
        success=all_ok,
        data=services,
        message="all services ready" if all_ok else "some services unavailable",
    )
