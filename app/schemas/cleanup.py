from pydantic import BaseModel

from app.schemas.base import BaseResponse


class CleanupExpiredSoftDeletedDataResponseData(BaseModel):
    deleted_users: int
    deleted_diaries: int
    deleted_images: int
    deleted_oauth_tokens: int
    deleted_password_reset_tokens: int
    deleted_ai_usage_logs: int
    deleted_emotion_stats: int
    deleted_email_verifications: int
    cutoff_date: str
    message: str


class CleanupExpiredSoftDeletedDataResponse(
    BaseResponse[CleanupExpiredSoftDeletedDataResponseData]
):
    pass


class GetSoftDeletedStatisticsResponseData(BaseModel):
    recent_users: int
    recent_diaries: int
    expired_users: int
    expired_diaries: int
    total_soft_deleted_users: int
    total_soft_deleted_diaries: int


class GetSoftDeletedStatisticsResponse(
    BaseResponse[GetSoftDeletedStatisticsResponseData]
):
    pass
