"""AI 사용 로그 생성 스키마"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.localization import LanguageCode


class CreateDiaryRequest(BaseModel):
    prompt: str = Field(
        ..., min_length=2, max_length=1000, description="사용자 입력 프롬프트"
    )
    style: Literal["poem", "short_story"] = Field(..., description="글쓰기 스타일")
    length: Literal["short", "medium", "long"] = Field(..., description="글쓰기 길이")
    emotion: str | None = Field(None, description="감정")
    regeneration_count: int = Field(1, ge=1, le=5, description="재생성 횟수 (1-5)")
    session_id: str | None = Field(None, description="재생성 세션 ID (UUID 문자열)")
    sessionId: str | None = Field(
        None, description="재생성 세션 ID (카멜케이스, 프론트엔드 호환)"
    )
    uploaded_images: list[dict] | None = Field(None, description="업로드된 이미지 정보")
    target_language: LanguageCode | None = Field(
        None,
        description="생성 결과를 원하는 언어 코드 (ko/en/ja)",
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        # None 값 체크
        if v is None:
            raise ValueError("프롬프트는 필수입니다.")

        # 빈 문자열 체크
        if not isinstance(v, str):
            raise ValueError("프롬프트는 유효한 문자열이어야 합니다.")

        if not v or len(v.strip()) < 2:
            raise ValueError("프롬프트는 최소 2자 이상이어야 합니다.")
        if len(v) > 1000:
            raise ValueError("프롬프트는 최대 1000자까지 입력 가능합니다.")
        return v.strip()


class AIUsageLogCreate(BaseModel):
    """AI 사용 로그 생성 요청 스키마"""

    user_id: str = Field(..., description="사용자 ID (UUID 문자열)")
    api_type: str = Field(..., description="API 타입 (generate/keywords)")
    session_id: str = Field(..., description="재생성 세션 ID (UUID 문자열)")
    regeneration_count: int = Field(1, ge=1, le=5, description="재생성 횟수 (1-5)")
    tokens_used: int = Field(0, ge=0, description="사용된 토큰 수")
    request_data: dict[str, Any] = Field(
        default_factory=dict, description="요청 데이터"
    )
    response_data: dict[str, Any] = Field(
        default_factory=dict, description="응답 데이터"
    )

    @field_validator("api_type")
    @classmethod
    def validate_api_type(cls, v):
        """API 타입 검증"""
        # None 값 체크
        if v is None:
            raise ValueError("API 타입은 필수입니다.")

        # 문자열 타입 체크
        if not isinstance(v, str):
            raise ValueError("API 타입은 유효한 문자열이어야 합니다.")

        if v not in ["generate", "keywords"]:
            raise ValueError("API 타입은 'generate' 또는 'keywords'여야 합니다.")
        return v

    @field_validator("regeneration_count")
    @classmethod
    def validate_regeneration_count(cls, v):
        """재생성 횟수 검증"""
        # None 값 체크
        if v is None:
            raise ValueError("재생성 횟수는 필수입니다.")

        # 숫자 타입 체크
        if not isinstance(v, int):
            raise ValueError("재생성 횟수는 정수여야 합니다.")

        if not (1 <= v <= 5):
            raise ValueError("재생성 횟수는 1-5 범위 내여야 합니다.")
        return v

    @field_validator("tokens_used")
    @classmethod
    def validate_tokens_used(cls, v):
        """토큰 수 검증"""
        # None 값 체크
        if v is None:
            raise ValueError("토큰 수는 필수입니다.")

        # 숫자 타입 체크
        if not isinstance(v, int):
            raise ValueError("토큰 수는 정수여야 합니다.")

        if v < 0:
            raise ValueError("토큰 수는 0 이상이어야 합니다.")
        return v

    @field_validator("user_id", "session_id")
    @classmethod
    def validate_uuid_format(cls, v):
        """UUID 형식 검증"""
        # None 값 체크
        if v is None:
            raise ValueError("UUID는 필수입니다.")

        # 문자열 타입 체크
        if not isinstance(v, str):
            raise ValueError("UUID는 유효한 문자열이어야 합니다.")

        from app.utils.validators import validate_uuid

        try:
            validate_uuid(v, "UUID")
            return v
        except Exception as e:
            raise ValueError("유효하지 않은 UUID 형식입니다.") from e

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "api_type": "generate",
                "session_id": "987fcdeb-51a2-43d1-9f12-345678901234",
                "regeneration_count": 1,
                "tokens_used": 150,
                "request_data": {
                    "prompt": "행복한 하루에 대한 글귀를 써줘",
                    "emotion": "happy",
                },
                "response_data": {
                    "generated_text": "오늘은 정말 행복한 하루였습니다...",
                    "confidence": 0.95,
                },
            }
        }


class AIUsageLogResponse(BaseModel):
    """AI 사용 로그 응답 스키마"""

    id: str = Field(..., description="로그 고유 ID")
    user_id: str = Field(..., description="사용자 ID")
    api_type: str = Field(..., description="API 타입")
    session_id: str = Field(..., description="재생성 세션 ID")
    regeneration_count: int = Field(..., description="재생성 횟수")
    tokens_used: int = Field(..., description="사용된 토큰 수")
    request_data: dict[str, Any] = Field(..., description="요청 데이터")
    response_data: dict[str, Any] = Field(..., description="응답 데이터")
    created_at: str = Field(..., description="생성일시")
    updated_at: str = Field(..., description="수정일시")

    class Config:
        from_attributes = True


class AIUsageLogListResponse(BaseModel):
    """AI 사용 로그 목록 응답 스키마"""

    logs: list[AIUsageLogResponse] = Field(..., description="AI 사용 로그 목록")
    total_count: int = Field(..., description="총 로그 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")

    class Config:
        from_attributes = True
