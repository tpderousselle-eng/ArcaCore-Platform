from typing import Any

from pydantic import BaseModel


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Any | None = None


def success_response(
    message: str,
    data: Any | None = None,
) -> APIResponse:
    return APIResponse(
        success=True,
        message=message,
        data=data,
    )


def error_response(
    message: str,
    data: Any | None = None,
) -> APIResponse:
    return APIResponse(
        success=False,
        message=message,
        data=data,
    )