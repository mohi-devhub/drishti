from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID

from drishti.connectors.base.errors import (
    AuthError,
    PermanentError,
    RateLimitError,
    TransientError,
)
from drishti.connectors.base.rate_limiter import RateLimitConfig, RateLimiter
from drishti.connectors.base.transport import Transport, TransportResponse


@dataclass(frozen=True)
class ConnectorConnection:
    id: UUID
    merchant_id: UUID
    source: str
    auth_payload: dict[str, Any]
    cursors: dict[str, Any]


class Connector(ABC):
    source: ClassVar[str]
    base_url: ClassVar[str]
    rate_limit_config: ClassVar[RateLimitConfig]

    def __init__(
        self,
        connection: ConnectorConnection,
        transport: Transport,
        rate_limiter: RateLimiter,
    ) -> None:
        self.connection = connection
        self.transport = transport
        self.rate_limiter = rate_limiter

    @abstractmethod
    async def authenticate(self) -> dict[str, str]: ...

    @abstractmethod
    async def refresh_credentials_if_needed(self) -> None: ...

    @abstractmethod
    def syncer(self, resource: str): ...

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> TransportResponse:
        await self.refresh_credentials_if_needed()
        headers = await self.authenticate()
        await self.rate_limiter.acquire(self.rate_limit_bucket, self.rate_limit_config)
        response = await self._request_with_retries(
            method,
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            headers=headers,
            params=params,
            json_body=json_body,
            timeout=timeout,
        )
        self._raise_for_status(response)
        return response

    @property
    def rate_limit_bucket(self) -> str:
        return f"{self.connection.merchant_id}:{self.source}"

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
        timeout: float,
    ) -> TransportResponse:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await self.transport.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json_body=json_body,
                    timeout=timeout,
                )
            except TransientError as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.25 * (2**attempt))
        raise last_error or TransientError("request failed")

    def _raise_for_status(self, response: TransportResponse) -> None:
        if response.status_code in (401, 403):
            raise AuthError(f"{self.source} authentication failed")
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                f"{self.source} rate limited request",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if 500 <= response.status_code:
            raise TransientError(f"{self.source} transient HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PermanentError(f"{self.source} permanent HTTP {response.status_code}")

