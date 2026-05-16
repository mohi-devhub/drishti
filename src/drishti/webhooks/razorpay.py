from __future__ import annotations

import hashlib
import hmac
from typing import Any


def verify_signature(*, body: bytes, header: str | None, secret: str | None) -> bool:
    if not secret:
        return True
    if not header:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header)


def resource_and_record(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    event = str(payload.get("event") or "")
    entity_group = event.split(".", 1)[0]
    if entity_group in {"payment", "refund", "settlement"}:
        resource = f"{entity_group}s"
        entity = payload.get("payload", {}).get(entity_group, {}).get("entity")
        if isinstance(entity, dict):
            return resource, entity
    return "payments", payload
