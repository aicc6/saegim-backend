"""
API 스키마
"""

from .base import BaseResponse, PaginatedResponse, PaginationInfo
from .diary import DiaryListResponseData, DiaryResponseData

__all__ = [
    "BaseResponse",
    "PaginatedResponse",
    "PaginationInfo",
    "DiaryResponseData",
    "DiaryListResponseData",
]
