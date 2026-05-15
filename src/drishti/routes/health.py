from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text


class HealthResponse(BaseModel):
    status: str
    service: str
    checked_at: datetime


class ReadinessResponse(BaseModel):
    status: str
    service: str
    checked_at: datetime
    checks: dict[str, str]


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="drishti-api",
        checked_at=datetime.now(UTC),
    )


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="drishti-api",
        checked_at=datetime.now(UTC),
    )


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    checked_at = datetime.now(UTC)
    checks: dict[str, str] = {}

    sessionmaker = request.app.state.db_sessionmaker
    try:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            revision = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        checks["db"] = "ok"
        checks["alembic"] = str(revision or "missing")
    except Exception:
        checks["db"] = "error"
        checks["alembic"] = "unknown"

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        checks["redis"] = getattr(request.app.state, "redis_error", None) or "unavailable"
    else:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "error"

    ready_status = "ok" if checks["db"] == "ok" and checks["redis"] == "ok" else "error"
    response = ReadinessResponse(
        status=ready_status,
        service="drishti-api",
        checked_at=checked_at,
        checks=checks,
    )
    return JSONResponse(
        status_code=(
            status.HTTP_200_OK if ready_status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content=response.model_dump(mode="json"),
    )
