from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_merchant_for_clerk_context(
    session: AsyncSession,
    *,
    clerk_user_id: str | None,
    clerk_org_id: str | None,
) -> UUID | None:
    result = await session.execute(
        text(
            """
            SELECT resolve_merchant_id_for_clerk(:clerk_user_id, :clerk_org_id)
            """
        ),
        {"clerk_user_id": clerk_user_id, "clerk_org_id": clerk_org_id},
    )
    return result.scalar_one_or_none()
