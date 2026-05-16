from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.config import get_settings
from drishti.db.repositories import connections

router = APIRouter(prefix="/connections", tags=["connections"])

SOURCES = {"shopify", "shiprocket", "razorpay"}


class ConnectionSummary(BaseModel):
    source: str
    status: str
    display_name: str
    connected_at: str | None = None
    updated_at: str | None = None
    last_synced_at: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectionsResponse(BaseModel):
    connections: list[ConnectionSummary]


class ShopifyStartRequest(BaseModel):
    shop: str


class ShopifyStartResponse(BaseModel):
    install_url: str
    shop: str


class ShiprocketConnectRequest(BaseModel):
    email: str
    password: str
    token: str | None = None
    account_id: str | None = None
    expires_at: datetime | None = None


class RazorpayConnectRequest(BaseModel):
    key_id: str
    key_secret: str
    account_id: str | None = None


class ConnectResponse(BaseModel):
    source: str
    status: str


@router.get("", response_model=ConnectionsResponse)
async def list_connections(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> ConnectionsResponse:
    session: AsyncSession = request.state.db
    rows = await connections.list_for_merchant(session, merchant_id=merchant_id)
    by_source = {row["source"]: row for row in rows}
    return ConnectionsResponse(
        connections=[_summarize(by_source.get(source), source=source) for source in sorted(SOURCES)]
    )


@router.post("/shopify/start", response_model=ShopifyStartResponse)
async def start_shopify_oauth(payload: ShopifyStartRequest) -> ShopifyStartResponse:
    settings = get_settings()
    if not settings.shopify_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SHOPIFY_API_KEY is not configured",
        )
    shop = _normalize_shop(payload.shop)
    params = {
        "client_id": settings.shopify_api_key,
        "scope": settings.shopify_scopes,
        "redirect_uri": settings.shopify_redirect_uri
        or f"{str(settings.web_origin).rstrip('/')}/connections/shopify/callback",
        "state": "drishti-shopify-install",
    }
    return ShopifyStartResponse(
        shop=shop,
        install_url=f"https://{shop}/admin/oauth/authorize?{urlencode(params)}",
    )


@router.post("/shopify/callback", response_model=ConnectResponse)
async def complete_shopify_oauth(
    payload: dict[str, str],
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> ConnectResponse:
    settings = get_settings()
    if not settings.shopify_api_key or not settings.shopify_api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shopify OAuth credentials are not configured",
        )
    shop = _normalize_shop(payload.get("shop", ""))
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Shopify code")
    if not _valid_shopify_hmac(payload, settings.shopify_api_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shopify HMAC")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_api_key,
                "client_secret": settings.shopify_api_secret,
                "code": code,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify token exchange failed",
        )
    token_payload = response.json()
    session: AsyncSession = request.state.db
    await connections.upsert_connection(
        session,
        merchant_id=merchant_id,
        source="shopify",
        auth_payload={
            "shop": shop,
            "access_token": token_payload.get("access_token"),
            "scopes": token_payload.get("scope", settings.shopify_scopes),
        },
    )
    return ConnectResponse(source="shopify", status="active")


@router.post("/shiprocket", response_model=ConnectResponse)
async def connect_shiprocket(
    payload: ShiprocketConnectRequest,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> ConnectResponse:
    token = payload.token or await _shiprocket_login(payload.email, payload.password)
    expires_at = payload.expires_at or datetime.now(UTC) + timedelta(days=9)
    session: AsyncSession = request.state.db
    await connections.upsert_connection(
        session,
        merchant_id=merchant_id,
        source="shiprocket",
        auth_payload={
            "email": payload.email,
            "password": payload.password,
            "token": token,
            "account_id": payload.account_id,
            "expires_at": expires_at.isoformat(),
        },
    )
    return ConnectResponse(source="shiprocket", status="active")


@router.post("/razorpay", response_model=ConnectResponse)
async def connect_razorpay(
    payload: RazorpayConnectRequest,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> ConnectResponse:
    session: AsyncSession = request.state.db
    await connections.upsert_connection(
        session,
        merchant_id=merchant_id,
        source="razorpay",
        auth_payload={
            "key_id": payload.key_id,
            "key_secret": payload.key_secret,
            "account_id": payload.account_id,
        },
    )
    return ConnectResponse(source="razorpay", status="active")


@router.delete("/{source}", response_model=ConnectResponse)
async def revoke_connection(
    source: str,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> ConnectResponse:
    if source not in SOURCES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown connection source")
    session: AsyncSession = request.state.db
    revoked = await connections.revoke(session, merchant_id=merchant_id, source=source)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return ConnectResponse(source=source, status="revoked")


async def _shiprocket_login(email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://apiv2.shiprocket.in/v1/external/auth/login",
            json={"email": email, "password": password},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shiprocket login failed",
        )
    token = response.json().get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shiprocket login did not return a token",
        )
    return str(token)


def _summarize(row: dict[str, Any] | None, *, source: str) -> ConnectionSummary:
    if row is None:
        return ConnectionSummary(source=source, status="not_connected", display_name=_source_name(source))
    auth_payload = dict(row["auth_payload"] or {})
    return ConnectionSummary(
        source=source,
        status=row["status"],
        display_name=_source_name(source),
        connected_at=row["created_at"].isoformat() if row["created_at"] else None,
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        last_synced_at=row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
        details=_safe_details(source, auth_payload),
    )


def _safe_details(source: str, auth_payload: dict[str, Any]) -> dict[str, Any]:
    if source == "shopify":
        return {"shop": auth_payload.get("shop"), "scopes": auth_payload.get("scopes")}
    if source == "shiprocket":
        return {
            "email": auth_payload.get("email"),
            "account_id": auth_payload.get("account_id"),
            "expires_at": auth_payload.get("expires_at"),
        }
    if source == "razorpay":
        return {"key_id": auth_payload.get("key_id"), "account_id": auth_payload.get("account_id")}
    return {}


def _normalize_shop(shop: str) -> str:
    normalized = shop.removeprefix("https://").removeprefix("http://").strip().strip("/").lower()
    if not normalized or "/" in normalized or not normalized.endswith(".myshopify.com"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shop must be a *.myshopify.com domain",
        )
    return normalized


def _valid_shopify_hmac(payload: dict[str, str], secret: str) -> bool:
    received = payload.get("hmac")
    if not received:
        return False
    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(payload.items())
        if key not in {"hmac", "signature"}
    )
    digest = hmac.new(secret.encode(), message.encode(), "sha256").hexdigest()
    return hmac.compare_digest(digest, received)


def _source_name(source: str) -> str:
    return {"shopify": "Shopify", "shiprocket": "Shiprocket", "razorpay": "Razorpay"}[source]
