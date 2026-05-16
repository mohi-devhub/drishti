from arq import cron
from arq.connections import RedisSettings

from drishti.config import get_settings
from drishti.db.session import create_engine, create_sessionmaker
from drishti.queue import DEFAULT_QUEUE_NAME
from drishti.workers.agent_worker import (
    agent_daily_run,
    enqueue_daily_agent_runs,
    run_rto_shipping_margin_agent,
)
from drishti.workers.normalize_worker import normalize_razorpay, normalize_shiprocket, normalize_shopify
from drishti.workers.sync_worker import (
    sync_razorpay_payments,
    sync_razorpay_refunds,
    sync_razorpay_settlements,
    sync_shiprocket_shipments,
    sync_shiprocket_tracking,
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
        sync_shiprocket_shipments,
        sync_shiprocket_tracking,
        sync_razorpay_payments,
        sync_razorpay_refunds,
        sync_razorpay_settlements,
        normalize_shopify,
        normalize_shiprocket,
        normalize_razorpay,
        run_rto_shipping_margin_agent,
        agent_daily_run,
        enqueue_daily_agent_runs,
    ]
    cron_jobs = [
        cron(enqueue_daily_agent_runs, name="enqueue_daily_agent_runs", hour=3, minute=0)
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    queue_name = DEFAULT_QUEUE_NAME
