from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from drishti.auth.clerk import ClerkJWTVerifier
from drishti.db.session import set_merchant_context

PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
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
        request.state.merchant_id = auth_context.merchant_id
        request.state.clerk_user_id = auth_context.clerk_user_id
        request.state.auth_claims = auth_context.claims

        async with self.sessionmaker() as session:
            async with session.begin():
                await set_merchant_context(session, auth_context.merchant_id)
                request.state.db = session
                response = await call_next(request)
        return response
