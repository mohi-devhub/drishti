from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth import get_current_merchant_id


class MerchantResponse(BaseModel):
    id: UUID
    name: str
    time_zone: str


router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("/me", response_model=MerchantResponse)
async def current_merchant(
    request: Request,
    merchant_id: UUID = Depends(get_current_merchant_id),
) -> MerchantResponse:
    session: AsyncSession = request.state.db
    row = (
        await session.execute(
            text(
                """
                SELECT id, name, time_zone
                FROM merchants
                WHERE id = :merchant_id
                """
            ),
            {"merchant_id": str(merchant_id)},
        )
    ).one()
    return MerchantResponse(id=row.id, name=row.name, time_zone=row.time_zone)
