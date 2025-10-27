"""다이어리 카테고리 API 스키마"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class DiaryCategoryCreateRequest(BaseModel):
    """카테고리 생성 요청"""

    name: str = Field(..., min_length=1, max_length=255, description="카테고리 이름")


class DiaryCategoryUpdateRequest(BaseModel):
    """카테고리 수정 요청"""

    name: str = Field(..., min_length=1, max_length=255, description="카테고리 이름")


class DiaryCategoryResponseData(BaseModel):
    """카테고리 응답 데이터"""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiaryCategoryResponse(BaseResponse[DiaryCategoryResponseData]):
    pass


class DiaryCategoryListResponse(BaseResponse[list[DiaryCategoryResponseData]]):
    pass
