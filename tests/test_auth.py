from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException

from drishti.auth.clerk import ClerkJWTVerifier
from drishti.config import Settings
from drishti.db.session import set_merchant_context

TEST_SECRET = "test-secret-with-at-least-thirty-two-bytes"


def verifier() -> ClerkJWTVerifier:
    return ClerkJWTVerifier(
        Settings(
            DRISHTI_TEST_JWT_SECRET=TEST_SECRET,
            CLERK_JWT_ISSUER="https://issuer.test",
            CLERK_JWT_AUDIENCE="drishti",
        )
    )


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))


@pytest.mark.asyncio
async def test_verifier_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await verifier().verify_authorization(None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await verifier().verify_authorization("Bearer not-a-jwt")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verifier_extracts_merchant_id_from_valid_token() -> None:
    merchant_id = UUID("00000000-0000-0000-0000-00000000000a")
    token = jwt.encode(
        {
            "sub": "user_123",
            "merchant_id": str(merchant_id),
            "iss": "https://issuer.test",
            "aud": "drishti",
        },
        TEST_SECRET,
        algorithm="HS256",
    )

    context = await verifier().verify_authorization(f"Bearer {token}")

    assert context.merchant_id == merchant_id
    assert context.clerk_user_id == "user_123"


@pytest.mark.asyncio
async def test_set_merchant_context_uses_parameter_safe_set_config() -> None:
    merchant_id = UUID("00000000-0000-0000-0000-00000000000a")
    session = FakeSession()

    await set_merchant_context(session, merchant_id)

    sql, params = session.calls[0]
    assert "set_config('app.current_merchant_id', :merchant_id, true)" in sql
    assert params == {"merchant_id": str(merchant_id)}
