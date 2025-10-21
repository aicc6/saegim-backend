from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.schemas.base import BaseResponse

settings = get_settings()


class CreateAiUsageLogRequest(BaseModel):
    api_type: Literal["keywords", "generate"]
    session_id: str
    regeneration_count: int = Field(
        1, description="재생성 횟수", ge=1, le=settings.ai_max_regeneration_count
    )
    tokens_used: int = Field(1, description="토큰 사용량", ge=0)
    request_data: dict[str, Any] | None = None
    response_data: dict[str, Any] | None = None


class CreateAiUsageLogResponseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    api_type: str
    session_id: UUID
    regeneration_count: int
    tokens_used: int | None
    request_data: dict[str, Any] | None
    response_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class CreateAiUsageLogResponse(BaseResponse[CreateAiUsageLogResponseData]):
    pass


class GetOriginalUserInputResponseData(BaseModel):
    original_input: str


class GetOriginalUserInputResponse(BaseResponse[GetOriginalUserInputResponseData]):
    pass


class PromptData(BaseModel):
    """프롬프트 데이터"""

    prompt: str | None = None


class GetAllPromptsResponseData(BaseModel):
    """모든 프롬프트 조회 응답 데이터"""

    prompts: list[PromptData]
    total_count: int


class GetAllPromptsResponse(BaseResponse[GetAllPromptsResponseData]):
    pass
