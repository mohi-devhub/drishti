from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


class Transport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> TransportResponse: ...


class LiveTransport:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> TransportResponse:
        response = await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout,
        )
        return TransportResponse(
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=response.content,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class MockTransport:
    """Replays fixture responses matched by method, path, and query params."""

    def __init__(self, fixture_dir: str | Path) -> None:
        self.fixture_dir = Path(fixture_dir)
        self._fixtures = self._load_fixtures()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> TransportResponse:
        fixture = self._match(method, url, params or {})
        response = fixture["response"]
        payload = response.get("json")
        body = response.get("body")
        if body is None and payload is not None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        return TransportResponse(
            status_code=int(response.get("status_code", 200)),
            headers={key.lower(): value for key, value in response.get("headers", {}).items()},
            body=body or b"",
        )

    def _load_fixtures(self) -> list[dict[str, Any]]:
        if not self.fixture_dir.exists():
            raise FileNotFoundError(f"Fixture directory does not exist: {self.fixture_dir}")
        fixtures: list[dict[str, Any]] = []
        for path in sorted(self.fixture_dir.rglob("*.json")):
            with path.open("rb") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                fixtures.extend(data)
            else:
                fixtures.append(data)
        return fixtures

    def _match(self, method: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        parsed = urlparse(url)
        normalized_params = _normalize_params(params)
        for fixture in self._fixtures:
            request = fixture.get("request", {})
            if request.get("method", "GET").upper() != method.upper():
                continue
            if request.get("path") != parsed.path:
                continue
            expected_params = _normalize_params(request.get("params", {}))
            if expected_params.items() <= normalized_params.items():
                return fixture
        raise LookupError(f"No fixture for {method.upper()} {parsed.path} {normalized_params}")


class RecordingTransport:
    def __init__(
        self,
        inner: Transport,
        fixture_dir: str | Path,
        *,
        sanitizer: "FixtureSanitizer | None" = None,
    ) -> None:
        self.inner = inner
        self.fixture_dir = Path(fixture_dir)
        self.sanitizer = sanitizer or default_sanitizer

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> TransportResponse:
        response = await self.inner.request(
            method,
            url,
            headers=headers,
            params=params,
            json_body=json_body,
            timeout=timeout,
        )
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        parsed = urlparse(url)
        payload = {
            "request": {
                "method": method.upper(),
                "path": parsed.path,
                "params": params or {},
            },
            "response": {
                "status_code": response.status_code,
                "headers": response.headers,
                "json": _json_or_text(response),
            },
        }
        payload = self.sanitizer(payload)
        digest = hashlib.sha256(
            json.dumps(payload["request"], sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        target = self.fixture_dir / f"{method.lower()}_{parsed.path.strip('/').replace('/', '_')}_{digest}.json"
        with target.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return response


FixtureSanitizer = Any


def default_sanitizer(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _json_or_text(response: TransportResponse) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return response.text


def _normalize_params(params: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in params.items() if value is not None}

