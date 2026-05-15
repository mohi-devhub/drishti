from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.chat.loop import run_chat_turn
from drishti.rate_limit import check_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: UUID | None = None


@router.post("")
async def chat(
    payload: ChatRequest,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    check_rate_limit(
        request,
        merchant_id=merchant_id,
        bucket="chat",
        limit=30,
        window_seconds=60,
    )
    return await run_chat_turn(
        session,
        merchant_id=merchant_id,
        message=payload.message,
        clerk_user_id=getattr(request.state, "clerk_user_id", "system"),
        chat_session_id=payload.session_id,
    )
