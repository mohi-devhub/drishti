from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from drishti.auth.clerk import ClerkJWTVerifier
from drishti.auth.middleware import MerchantScopeMiddleware
from drishti.config import get_settings
from drishti.db.session import create_engine, create_sessionmaker
from drishti.observability import configure_observability
from drishti.routes.agents import router as agents_router
from drishti.routes.chat import router as chat_router
from drishti.routes.health import router as health_router
from drishti.routes.merchants import router as merchants_router
from drishti.routes.webhooks_shopify import router as shopify_webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    yield
    if hasattr(app.state, "db_engine"):
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_observability(settings)
    app = FastAPI(title="Drishti API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.web_origin).rstrip("/")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    logfire.instrument_fastapi(app)
    app.include_router(health_router)
    app.include_router(merchants_router)
    app.include_router(chat_router)
    app.include_router(agents_router)
    app.include_router(shopify_webhooks_router)
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
