from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.chat.loop import run_chat_turn

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
    return await run_chat_turn(
        session,
        merchant_id=merchant_id,
        message=payload.message,
        clerk_user_id=getattr(request.state, "clerk_user_id", "system"),
        chat_session_id=payload.session_id,
    )
