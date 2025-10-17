"""
기본 API 응답 스키마
"""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """기본 응답 모델"""

    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class StringResponse(BaseResponse[str]):
    pass


class MessageResponseData(BaseModel):
    message: str


class MessageResponse(BaseResponse[MessageResponseData]):
    pass


class PaginationInfo(BaseModel):
    """페이지네이션 정보"""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """페이지네이션 응답 모델"""

    success: bool = True
    data: list[T]
    pagination: PaginationInfo
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
