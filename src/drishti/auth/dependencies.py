from uuid import UUID

from fastapi import Request


def get_current_merchant_id(request: Request) -> UUID:
    return request.state.merchant_id
