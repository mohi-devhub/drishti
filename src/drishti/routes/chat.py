from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.chat.loop import run_chat_turn
from drishti.db.repositories import chat as chat_repo
from drishti.rate_limit import check_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: UUID | None = None


@router.get("/sessions")
async def list_chat_sessions(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
    limit: int = 30,
) -> dict:
    session: AsyncSession = request.state.db
    rows = await chat_repo.list_sessions(
        session,
        merchant_id=merchant_id,
        clerk_user_id=getattr(request.state, "clerk_user_id", None),
        limit=limit,
    )
    return {"sessions": [_serialize_session(row) for row in rows]}


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: UUID,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    rows = await chat_repo.list_messages(session, merchant_id=merchant_id, session_id=session_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return {
        "session_id": str(session_id),
        "messages": [_serialize_message(row) for row in rows],
    }


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


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> StreamingResponse:
    session: AsyncSession = request.state.db
    check_rate_limit(
        request,
        merchant_id=merchant_id,
        bucket="chat",
        limit=30,
        window_seconds=60,
    )

    async def events():
        yield _sse("status", {"status": "accepted"})
        result = await run_chat_turn(
            session,
            merchant_id=merchant_id,
            message=payload.message,
            clerk_user_id=getattr(request.state, "clerk_user_id", "system"),
            chat_session_id=payload.session_id,
        )
        yield _sse(
            "metadata",
            {
                "session_id": result["session_id"],
                "message_id": result["message_id"],
                "validation_status": result["validation_status"],
                "openai_status": result["openai_status"],
                "tool_results": result["tool_results"],
            },
        )
        for chunk in _answer_chunks(result["answer"]):
            yield _sse("delta", {"text": chunk})
        yield _sse("done", {"answer": result["answer"]})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _answer_chunks(answer: str) -> list[str]:
    chunks: list[str] = []
    buffer = ""
    for token in answer.split(" "):
        next_buffer = f"{buffer} {token}".strip()
        if len(next_buffer) >= 32:
            chunks.append(next_buffer + " ")
            buffer = ""
        else:
            buffer = next_buffer
    if buffer:
        chunks.append(buffer)
    return chunks


def _serialize_session(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "clerk_user_id": row["clerk_user_id"],
        "message_count": int(row["message_count"] or 0),
        "latest_message": row["latest_message"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _serialize_message(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "role": row["role"],
        "content": row["content"],
        "tool_call_id": str(row["tool_call_id"]) if row["tool_call_id"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
