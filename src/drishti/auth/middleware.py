from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from drishti.auth.clerk import ClerkJWTVerifier
from drishti.db.repositories.auth import resolve_merchant_for_clerk_context
from drishti.db.session import set_merchant_context

PUBLIC_PATHS = {"/health", "/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PREFIXES = ("/webhooks/shopify/", "/demo/token/")


class MerchantScopeMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        verifier: ClerkJWTVerifier,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(app)
        self.verifier = verifier
        self.sessionmaker = sessionmaker

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method == "OPTIONS"
            or request.url.path in PUBLIC_PATHS
            or request.url.path.startswith(PUBLIC_PREFIXES)
        ):
            return await call_next(request)

        try:
            auth_context = await self.verifier.verify_authorization(
                request.headers.get("authorization")
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        async with self.sessionmaker() as session:
            merchant_id = auth_context.merchant_id
            if merchant_id is None:
                merchant_id = await resolve_merchant_for_clerk_context(
                    session,
                    clerk_user_id=auth_context.clerk_user_id,
                    clerk_org_id=auth_context.clerk_org_id,
                )
            if merchant_id is None:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "No merchant mapping for Clerk identity"},
                )

            await set_merchant_context(session, merchant_id)
            await session.commit()
            request.state.merchant_id = merchant_id
            request.state.clerk_user_id = auth_context.clerk_user_id
            request.state.auth_claims = auth_context.claims
            request.state.auth_mode = auth_context.auth_mode
            request.state.db = session
            response = await call_next(request)
            if session.in_transaction():
                await session.commit()
        return response
