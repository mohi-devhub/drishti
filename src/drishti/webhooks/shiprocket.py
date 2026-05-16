from __future__ import annotations

import hmac
from typing import Any


def verify_secret(*, header: str | None, secret: str | None) -> bool:
    if not secret:
        return True
    if not header:
        return False
    return hmac.compare_digest(header, secret)


def resource_from_payload(payload: dict[str, Any], topic: str) -> str:
    normalized_topic = topic.lower()
    if "track" in normalized_topic or payload.get("tracking_data") or payload.get("awb"):
        return "tracking"
    return "shipments"
