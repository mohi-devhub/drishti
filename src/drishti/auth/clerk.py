from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
import anyio
from fastapi import HTTPException, status
from jwt import PyJWKClient

from drishti.config import Settings


@dataclass(frozen=True)
class AuthContext:
    merchant_id: UUID | None
    clerk_user_id: str | None
    clerk_org_id: str | None
    claims: dict[str, Any]
    auth_mode: str


class ClerkJWTVerifier:
    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.clerk_jwt_issuer
        self._audience = settings.clerk_jwt_audience
        self._allow_demo_hs256 = settings.environment == "local" and settings.allow_local_demo_auth
        self._test_secret = settings.test_jwt_secret if self._allow_demo_hs256 else None
        self._jwk_client: PyJWKClient | None = None
        if self._issuer:
            jwks_url = f"{self._issuer.rstrip('/')}/.well-known/jwks.json"
            self._jwk_client = PyJWKClient(jwks_url)

    async def verify_authorization(self, authorization: str | None) -> AuthContext:
        token = self._extract_bearer_token(authorization)
        claims, auth_mode = await self._decode(token)
        return AuthContext(
            merchant_id=self._extract_merchant_id(claims) if auth_mode == "demo" else None,
            clerk_user_id=claims.get("sub"),
            clerk_org_id=self._extract_org_id(claims),
            claims=claims,
            auth_mode=auth_mode,
        )

    def _extract_bearer_token(self, authorization: str | None) -> str:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token

    async def _decode(self, token: str) -> tuple[dict[str, Any], str]:
        try:
            if self._test_secret:
                claims = jwt.decode(
                    token,
                    self._test_secret,
                    algorithms=["HS256"],
                    audience=self._audience,
                    issuer=self._issuer,
                    options={
                        "verify_aud": self._audience is not None,
                        "verify_iss": self._issuer is not None,
                    },
                )
                return claims, "demo"
            if not self._jwk_client:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Clerk JWT issuer is not configured",
                )
            signing_key = await self._get_signing_key(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_aud": self._audience is not None},
            )
            return claims, "clerk"
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    async def _get_signing_key(self, token: str) -> Any:
        assert self._jwk_client is not None
        return await anyio.to_thread.run_sync(self._jwk_client.get_signing_key_from_jwt, token)

    def _extract_merchant_id(self, claims: dict[str, Any]) -> UUID:
        merchant_id = claims.get("merchant_id") or claims.get("org_id")
        if not merchant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT is missing merchant_id claim",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return UUID(str(merchant_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT merchant_id claim is invalid",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def _extract_org_id(self, claims: dict[str, Any]) -> str | None:
        org_id = claims.get("org_id") or claims.get("organization_id")
        return str(org_id) if org_id else None
