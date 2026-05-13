from __future__ import annotations

import base64
import hashlib
import hmac


def verify_hmac(*, body: bytes, header: str | None, secret: str | None) -> bool:
    if not secret:
        return True
    if not header:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, header)


def resource_from_topic(topic: str) -> str:
    prefix = topic.split("/", 1)[0]
    if prefix == "orders":
        return "orders"
    if prefix == "customers":
        return "customers"
    if prefix == "products":
        return "products"
    return prefix
