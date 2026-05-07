from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field
import time

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "ok"
    timestamp: float = Field(default_factory=time.time)


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str
    message: str
    detail: Any = None
    timestamp: float = Field(default_factory=time.time)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size
