"""
다이어리 API 스키마 (캘린더용)
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import BaseResponse
from app.utils.validators import convert_uuid_to_string, parse_keywords_from_json


class HandwritingToDiaryRequest(BaseModel):
    image_url: str = Field(
        ..., description="손글씨 이미지의 원본 URL (MinIO 업로드 결과)"
    )
    style: str = Field(
        "short_story", description="글쓰기 스타일 (short_story, poem 등)"
    )
    length: str = Field("medium", description="문단 길이 (short, medium, long)")
    user_emotion: str | None = Field(
        None, description="사용자가 선택한 감정 (happy, sad, angry, peaceful, unrest)"
    )
    uploaded_images: list[dict] | None = Field(
        None, description="함께 저장할 이미지정보(옵션)"
    )
    save: bool = Field(
        True,
        description="다이어리를 실제로 저장할지 여부 (True: 저장, False: 미리보기만)",
    )

    @field_validator("user_emotion")
    @classmethod
    def validate_user_emotion(cls, v: Any):
        """사용자 감정 값 검증"""
        if v is not None:
            allowed_emotions = ["happy", "sad", "angry", "peaceful", "unrest"]
            if v not in allowed_emotions:
                raise ValueError(
                    f"감정은 {allowed_emotions} 중 하나여야 합니다. 입력된 값: {v}"
                )
        return v


class ImageResponse(BaseModel):
    """이미지 응답 스키마"""

    id: str
    file_path: str
    thumbnail_path: str | None = None
    mime_type: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)

    class Config:
        from_attributes = True


class DiaryResponseData(BaseModel):
    """다이어리 응답 스키마"""

    id: str
    title: str | None
    content: str
    user_emotion: str | None = None
    ai_emotion: str | None = None
    ai_emotion_confidence: float | None = None
    user_id: str
    ai_generated_text: str | None = None
    ocr_text: str | None = None  # 손글씨 인식으로 추출된 원본 텍스트
    is_public: bool
    keywords: list[str] | None = None  # keywords를 리스트 타입으로 수정
    diary_date: date | None = None  # 다이어리 작성 날짜
    created_at: datetime
    updated_at: datetime | None = None
    images: list[ImageResponse] | None = None  # 이미지 정보 추가

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)

    @field_validator("keywords", mode="before")
    @classmethod
    def parse_keywords(cls, v: Any):
        """keywords를 JSON 문자열에서 리스트로 변환"""
        return parse_keywords_from_json(v)

    class Config:
        from_attributes = True


class DiaryResponse(BaseResponse[DiaryResponseData]):
    pass


class DiaryListResponseData(BaseModel):
    """다이어리 목록 응답 스키마 (캘린더용)"""

    id: str
    title: str | None
    content: str  # 수정된 본문 내용을 표시하기 위해 content 필드 추가
    ai_generated_text: str | None = None  # ai_generated_text 필드 추가
    ocr_text: str | None = None  # 손글씨 인식으로 추출된 원본 텍스트
    user_emotion: str | None = None
    ai_emotion: str | None = None
    keywords: list[str] | None = None  # keywords를 리스트 타입으로 수정
    diary_date: date | None = None  # 다이어리 작성 날짜
    created_at: datetime
    is_public: bool
    images: list[ImageResponse] | None = None  # 이미지 정보 추가

    @field_validator("id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)

    @field_validator("keywords", mode="before")
    @classmethod
    def parse_keywords(cls, v: Any):
        """keywords를 JSON 문자열에서 리스트로 변환"""
        return parse_keywords_from_json(v)

    class Config:
        from_attributes = True


class DiaryListResponse(BaseResponse[list[DiaryListResponseData]]):
    pass


class GetDiaryImageResponseData(BaseModel):
    id: UUID
    file_path: str
    thumbnail_path: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    created_at: str


class GetDiaryImageResponse(BaseResponse[list[GetDiaryImageResponseData]]):
    pass


class UploadImageResponseData(BaseModel):
    """이미지 업로드 응답 스키마"""

    id: UUID
    file_path: str
    thumbnail_path: str | None
    mime_type: str | None
    file_size: int | None


class UploadImageResponse(BaseResponse[UploadImageResponseData]):
    pass


class UploadImagesResponse(BaseResponse[list[UploadImageResponseData]]):
    pass


class UploadHandWritingImageResponseData(BaseModel):
    """손글씨 이미지 업로드 응답 스키마"""

    file_id: UUID
    original_url: str
    thumbnail_url: str | None
    mime_type: str | None
    file_size: int | None
    filename: str | None


class UploadHandWritingImageResponse(BaseResponse[UploadHandWritingImageResponseData]):
    pass


class UploadHandWritingImagesResponse(
    BaseResponse[list[UploadHandWritingImageResponseData]]
):
    pass


class DiaryCreateRequestImage(BaseModel):
    """다이어리 생성 요청 이미지 스키마"""

    original_url: str = Field(..., description="이미지 파일 경로")
    thumbnail_url: str | None = Field(None, description="썸네일 파일 경로")
    mime_type: str | None = Field(None, description="이미지 MIME 타입")
    file_size: int | None = Field(None, description="이미지 파일 크기")


class DiaryCreateRequest(BaseModel):
    """다이어리 생성 요청 스키마"""

    title: str | None = Field(None, description="다이어리 제목")
    content: str = Field(
        ..., min_length=1, description="다이어리 내용 (사용자 원본 프롬프트)"
    )
    user_emotion: str | None = Field(None, description="사용자가 선택한 감정")
    ai_generated_text: str | None = Field(None, description="AI가 생성한 텍스트")
    ocr_text: str | None = Field(None, description="손글씨 인식으로 추출된 원본 텍스트")
    ai_emotion: str | None = Field(None, description="AI가 분석한 감정")
    ai_emotion_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="AI 감정 분석 신뢰도"
    )
    keywords: list[str] | None = Field(None, description="AI가 추출한 키워드")
    diary_date: date | None = Field(
        None, description="다이어리 작성 날짜 (사용자가 선택한 날짜)"
    )
    uploaded_images: list[DiaryCreateRequestImage] | None = Field(
        None, description="업로드된 이미지 정보 (AI 생성 시)"
    )

    @field_validator("user_emotion", "ai_emotion")
    @classmethod
    def validate_emotion(cls, v: Any):
        """감정 값 검증"""
        if v is not None:
            allowed_emotions = ["happy", "sad", "angry", "peaceful", "unrest"]
            if v not in allowed_emotions:
                raise ValueError(f"감정은 {allowed_emotions} 중 하나여야 합니다")
        return v

    class Config:
        from_attributes = True


class DiaryUpdateRequest(BaseModel):
    """다이어리 수정 요청 스키마"""

    title: str | None = None
    content: str | None = None
    ai_generated_text: str | None = None
    user_emotion: str | None = None
    keywords: list[str] | None = None
    diary_date: date | None = None

    @field_validator("keywords", mode="before")
    @classmethod
    def parse_keywords(cls, v: Any):
        """keywords를 JSON 문자열에서 리스트로 변환"""
        return parse_keywords_from_json(v)

    class Config:
        from_attributes = True


class DiaryContentResponseData(BaseModel):
    """다이어리 content만 조회 응답 스키마"""

    id: str
    content: str

    @field_validator("id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)

    class Config:
        from_attributes = True


class DiaryContentResponse(BaseResponse[DiaryContentResponseData]):
    pass
