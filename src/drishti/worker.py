from arq.connections import RedisSettings

from drishti.config import get_settings


async def health_check(ctx: dict) -> str:
    return "ok"


def redis_settings() -> RedisSettings:
    settings = get_settings()
    redis_url = str(settings.redis_url)
    return RedisSettings.from_dsn(redis_url)


class WorkerSettings:
    functions = [health_check]
    redis_settings = redis_settings()
    queue_name = "drishti:default"
