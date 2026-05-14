from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from drishti.auth.clerk import LOCAL_DEMO_JWT_SECRET
from drishti.config import get_settings

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoTokenResponse(BaseModel):
    merchant_id: UUID
    merchant_key: str
    token: str


DEMO_MERCHANTS = {
    "merchant_a": UUID("00000000-0000-0000-0000-00000000000a"),
    "merchant_b": UUID("00000000-0000-0000-0000-00000000000b"),
    "merchant_c": UUID("00000000-0000-0000-0000-00000000000c"),
}


@router.get("/token/{merchant_key}", response_model=DemoTokenResponse)
async def demo_token(merchant_key: str) -> DemoTokenResponse:
    settings = get_settings()
    if settings.environment != "local":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo token endpoint is only available in local mode",
        )
    secret = settings.test_jwt_secret or LOCAL_DEMO_JWT_SECRET
    merchant_id = DEMO_MERCHANTS.get(merchant_key)
    if merchant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown demo merchant")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": f"demo_user_{merchant_key}",
            "merchant_id": str(merchant_id),
            "iss": settings.clerk_jwt_issuer,
            "aud": settings.clerk_jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=8)).timestamp()),
        },
        secret,
        algorithm="HS256",
    )
    return DemoTokenResponse(merchant_id=merchant_id, merchant_key=merchant_key, token=token)
