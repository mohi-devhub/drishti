from arq.connections import RedisSettings

from drishti.config import get_settings
from drishti.db.session import create_engine, create_sessionmaker
from drishti.workers.normalize_worker import normalize_shopify
from drishti.workers.sync_worker import (
    sync_shopify_customers,
    sync_shopify_orders,
    sync_shopify_products,
)


async def health_check(ctx: dict) -> str:
    return "ok"


async def startup(ctx: dict) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["settings"] = settings
    ctx["db_engine"] = engine
    ctx["db_sessionmaker"] = create_sessionmaker(engine)


async def shutdown(ctx: dict) -> None:
    await ctx["db_engine"].dispose()


def redis_settings() -> RedisSettings:
    settings = get_settings()
    redis_url = str(settings.redis_url)
    return RedisSettings.from_dsn(redis_url)


class WorkerSettings:
    functions = [
        health_check,
        sync_shopify_orders,
        sync_shopify_customers,
        sync_shopify_products,
        normalize_shopify,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    queue_name = "drishti:default"
