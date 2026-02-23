from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    message: str
