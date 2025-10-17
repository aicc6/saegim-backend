"""
알림 시스템 관련 스키마
FCM (Firebase Cloud Messaging) 및 인앱 알림 통합 스키마
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseResponse
from app.utils.validators import convert_uuid_to_string


class DeviceType(str, Enum):
    """디바이스 타입"""

    WEB = "web"
    ANDROID = "android"
    IOS = "ios"


class NotificationStatus(str, Enum):
    """알림 상태"""

    SENT = "sent"
    FAILED = "failed"
    PENDING = "pending"
    DELIVERED = "delivered"
    OPENED = "opened"


class NotificationType(str, Enum):
    """알림 타입"""

    DIARY_REMINDER = "diary_reminder"
    AI_CONTENT_READY = "ai_content_ready"
    EMOTION_TREND = "emotion_trend"
    ANNIVERSARY = "anniversary"
    FRIEND_SHARE = "friend_share"
    GENERAL = "general"


class NotificationFrequency(str, Enum):
    """알림 주기"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NEVER = "never"


# Request Schemas
class RegisterFcmTokenRequest(BaseModel):
    """FCM 토큰 등록 요청"""

    model_config = ConfigDict(from_attributes=True)

    token: str = Field(..., description="FCM 토큰", max_length=255)
    device_type: DeviceType = Field(..., description="디바이스 타입")
    device_info: dict[str, Any] | None = Field(None, description="디바이스 정보")
    app_version: str | None = Field(None, description="앱 버전", max_length=50)


class FCMTokenCreate(BaseModel):
    """FCM 토큰 등록 요청"""

    model_config = ConfigDict(from_attributes=True)

    token: str = Field(..., description="FCM 토큰", max_length=255)
    device_type: DeviceType = Field(..., description="디바이스 타입")
    device_info: dict[str, Any] | None = Field(None, description="디바이스 정보")


class SendNotificationRequest(BaseModel):
    """알림 전송 요청"""

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., description="알림 제목", max_length=255)
    body: str = Field(..., description="알림 내용", max_length=1000)
    notification_type: str = Field(..., description="알림 타입")
    user_ids: list[UUID] = Field(..., description="대상 사용자 ID 목록")
    data: dict[str, Any] | None = Field(None, description="추가 데이터")


class NotificationSettingsUpdate(BaseModel):
    """알림 설정 업데이트 요청 - notification_settings 테이블 구조와 일치"""

    model_config = ConfigDict(from_attributes=True)

    push_enabled: bool | None = Field(None, description="푸시 알림 전체 활성화")
    diary_reminder_enabled: bool | None = Field(
        None, description="다이어리 리마인더 활성화"
    )
    diary_reminder_time: str | None = Field(
        None, description="다이어리 리마인더 시간 (HH:MM 형식)", max_length=5
    )
    diary_reminder_days: list[str] | None = Field(
        None,
        description="다이어리 리마인더 요일 ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']",
    )
    report_notification_enabled: bool | None = Field(
        None, description="리포트 알림 활성화"
    )
    ai_processing_enabled: bool | None = Field(
        None, description="AI 처리 완료 알림 활성화"
    )
    browser_push_enabled: bool | None = Field(
        None, description="브라우저 푸시 알림 활성화"
    )

    @field_validator("diary_reminder_time")
    @classmethod
    def validate_time_format(cls, v: Any):
        """시간 형식 검증 (HH:MM)"""
        if v is not None:
            import re

            if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
                raise ValueError("시간은 HH:MM 형식이어야 합니다 (예: 21:00)")
        return v

    @field_validator("diary_reminder_days")
    @classmethod
    def validate_weekdays(cls, v: Any):
        """요일 배열 검증"""
        if v is not None:
            valid_days = {
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            }
            for day in v:
                if day.lower() not in valid_days:
                    raise ValueError(
                        f"유효하지 않은 요일: {day}. 가능한 값: {valid_days}"
                    )
        return v


class TestNotificationCreate(BaseModel):
    """테스트 알림 전송 요청"""

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(default="test", description="알림 타입")
    title: str = Field(..., description="알림 제목", max_length=255)
    message: str = Field(..., description="알림 메시지", max_length=1000)
    data: dict[str, Any] | None = Field(None, description="추가 데이터")


class DiaryNotificationCreate(BaseModel):
    """다이어리 알림 전송 요청"""

    model_config = ConfigDict(from_attributes=True)

    type: NotificationType = Field(..., description="알림 타입")
    diary_id: UUID | None = Field(None, description="다이어리 ID")
    title: str = Field(..., description="알림 제목", max_length=255)
    message: str = Field(..., description="알림 메시지", max_length=1000)
    data: dict[str, Any] | None = Field(None, description="추가 데이터")


# Response Schemas
class RegisterFcmTokenResponseData(BaseModel):
    """FCM 토큰 응답"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token: str
    device_type: DeviceType
    device_info: dict[str, Any] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class RegisterFcmTokenResponse(BaseResponse[RegisterFcmTokenResponseData]):
    pass


class GetFcmTokensResponse(BaseResponse[list[RegisterFcmTokenResponseData]]):
    pass


class NotificationSettingsResponseData(BaseModel):
    """알림 설정 응답 - notification_settings 테이블 구조와 일치"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    push_enabled: bool
    diary_reminder_enabled: bool
    diary_reminder_time: str | None = Field(
        None, description="다이어리 리마인더 시간 (HH:MM 형식)"
    )
    diary_reminder_days: list[str] | None = Field(
        None, description="다이어리 리마인더 요일 ['monday','tuesday',...]"
    )
    report_notification_enabled: bool
    ai_processing_enabled: bool
    browser_push_enabled: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)


class NotificationSettingsResponse(BaseResponse[NotificationSettingsResponseData]):
    pass


class SendNotificationResponseData(BaseModel):
    """알림 전송 응답"""

    model_config = ConfigDict(from_attributes=True)

    success_count: int
    failure_count: int
    successful_tokens: list[str]
    failed_tokens: list[str]
    message: str


class SendNotificationResponse(BaseResponse[SendNotificationResponseData]):
    pass


class NotificationHistoryResponseData(BaseModel):
    """알림 목록 응답 (프론트 사용 필드만)"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: str
    notification_type: str
    status: str
    created_at: datetime
    fcm_response: dict[str, Any] | None = Field(None, description="FCM/부가 데이터")

    @field_validator("id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any):
        """UUID를 문자열로 변환"""
        return convert_uuid_to_string(v)


class NotificationHistoryResponse(BaseResponse[list[NotificationHistoryResponseData]]):
    pass


class MarkNotificationAsReadResponseData(BaseModel):
    notification_id: UUID
    updated_histories: int
    read_at: str


class MarkNotificationAsReadResponse(BaseResponse[MarkNotificationAsReadResponseData]):
    pass


class MarkNotificationsAsReadResponseData(BaseModel):
    updated_notifications: int
    updated_histories: int
    read_at: str


class MarkNotificationsAsReadResponse(
    BaseResponse[MarkNotificationsAsReadResponseData]
):
    pass


class DeleteNotificationResponseData(BaseModel):
    notification_id: str
    deleted: bool


class DeleteNotificationResponse(BaseResponse[DeleteNotificationResponseData]):
    pass


class FCMTokenListResponse(BaseModel):
    """FCM 토큰 목록 응답"""

    model_config = ConfigDict(from_attributes=True)

    tokens: list[RegisterFcmTokenResponseData]
    total: int
