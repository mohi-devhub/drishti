from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import logfire
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from drishti.auth.clerk import ClerkJWTVerifier
from drishti.auth.middleware import MerchantScopeMiddleware
from drishti.config import get_settings
from drishti.db.session import create_engine, create_sessionmaker
from drishti.middleware.request_id import RequestIDMiddleware
from drishti.observability import configure_observability
from drishti.routes.agents import router as agents_router
from drishti.routes.chat import router as chat_router
from drishti.routes.connections import router as connections_router
from drishti.routes.demo import router as demo_router
from drishti.routes.findings import router as findings_router
from drishti.routes.health import router as health_router
from drishti.routes.merchants import router as merchants_router
from drishti.routes.source_records import router as source_records_router
from drishti.routes.webhooks_shopify import router as shopify_webhooks_router
from drishti.routes.webhooks_shiprocket import router as shiprocket_webhooks_router
from drishti.routes.webhooks_razorpay import router as razorpay_webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.redis = None
    app.state.redis_error = None
    try:
        app.state.redis = await create_pool(RedisSettings.from_dsn(str(settings.redis_url)))
        await app.state.redis.ping()
    except Exception:
        app.state.redis_error = "Redis connection failed"
        if settings.environment != "local":
            raise
    yield
    if getattr(app.state, "redis", None) is not None:
        await app.state.redis.close()
    if hasattr(app.state, "db_engine"):
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_observability(settings)
    app = FastAPI(title="Drishti API", version="0.1.0", lifespan=lifespan)

    cors_origins = {str(settings.web_origin).rstrip("/")}
    cors_origins.update(
        origin.strip().rstrip("/")
        for origin in settings.extra_cors_origins.split(",")
        if origin.strip()
    )
    if settings.environment == "local":
        cors_origins.update({"http://localhost:3000", "http://localhost:3001"})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-request-id"],
        expose_headers=["x-request-id"],
    )
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sessionmaker
    app.add_middleware(
        MerchantScopeMiddleware,
        verifier=ClerkJWTVerifier(settings),
        sessionmaker=sessionmaker,
    )
    app.add_middleware(RequestIDMiddleware)

    logfire.instrument_fastapi(app)
    app.include_router(health_router)
    app.include_router(merchants_router)
    app.include_router(connections_router)
    app.include_router(chat_router)
    app.include_router(agents_router)
    app.include_router(shopify_webhooks_router)
    app.include_router(shiprocket_webhooks_router)
    app.include_router(razorpay_webhooks_router)
    app.include_router(source_records_router)
    app.include_router(findings_router)
    app.include_router(demo_router)
    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "drishti.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
    )
