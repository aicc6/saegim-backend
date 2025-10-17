from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class CreateInquiryRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=100, description="문의 제목")
    content: str = Field(..., min_length=10, max_length=1000, description="문의 내용")
    image_attached: bool = Field(default=False, description="이미지 첨부 여부")
    image_data: str | None = Field(
        default=None, description="Base64 인코딩된 이미지 데이터"
    )
    image_filename: str | None = Field(default=None, description="이미지 파일명")
    image_type: str | None = Field(default=None, description="이미지 MIME 타입")


# 문의 응답 모델
class SupportInquiryResponseData(BaseModel):
    message: str
    inquiry_id: str
    created_at: datetime


class CreateInquiryResponse(BaseResponse[SupportInquiryResponseData]):
    pass
