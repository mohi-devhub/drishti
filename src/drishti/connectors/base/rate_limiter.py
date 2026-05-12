from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RateLimitConfig:
    requests_per_second: float
    burst: int


class RateLimiter(Protocol):
    async def acquire(self, bucket: str, config: RateLimitConfig) -> None: ...


class NoopRateLimiter:
    async def acquire(self, bucket: str, config: RateLimitConfig) -> None:
        return None


class RedisRateLimiter:
    """Redis-backed token bucket shared across worker processes."""

    _SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])

local state = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(state[1])
local updated_at = tonumber(state[2])

if tokens == nil then
  tokens = burst
  updated_at = now_ms
end

local elapsed = math.max(0, now_ms - updated_at) / 1000
tokens = math.min(burst, tokens + (elapsed * rate))

if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HMSET', key, 'tokens', tokens, 'updated_at', now_ms)
  redis.call('PEXPIRE', key, ttl_ms)
  return 0
end

local wait_ms = math.ceil(((1 - tokens) / rate) * 1000)
redis.call('HMSET', key, 'tokens', tokens, 'updated_at', now_ms)
redis.call('PEXPIRE', key, ttl_ms)
return wait_ms
"""

    def __init__(self, redis: Any, *, namespace: str = "drishti:rate") -> None:
        self.redis = redis
        self.namespace = namespace

    async def acquire(self, bucket: str, config: RateLimitConfig) -> None:
        if config.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if config.burst <= 0:
            raise ValueError("burst must be positive")

        key = f"{self.namespace}:{bucket}"
        ttl_ms = max(1000, int((config.burst / config.requests_per_second) * 2000))
        while True:
            wait_ms = await self.redis.eval(
                self._SCRIPT,
                1,
                key,
                str(int(time.time() * 1000)),
                str(config.requests_per_second),
                str(config.burst),
                str(ttl_ms),
            )
            if int(wait_ms) <= 0:
                return
            await asyncio.sleep(int(wait_ms) / 1000)
