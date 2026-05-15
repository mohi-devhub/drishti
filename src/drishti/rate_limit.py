from __future__ import annotations

from time import monotonic
from uuid import UUID

from fastapi import HTTPException, Request, status


def check_rate_limit(
    request: Request,
    *,
    merchant_id: UUID,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = monotonic()
    state = getattr(request.app.state, "rate_limits", None)
    if state is None:
        state = {}
        request.app.state.rate_limits = state

    key = (str(merchant_id), bucket)
    window_start, count = state.get(key, (now, 0))
    if now - window_start >= window_seconds:
        window_start, count = now, 0
    count += 1
    state[key] = (window_start, count)

    if count > limit:
        retry_after = max(1, int(window_seconds - (now - window_start)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
