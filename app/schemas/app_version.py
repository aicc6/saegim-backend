"""
앱 버전 스키마
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class PlatformType(str, Enum):
    """플랫폼 타입"""

    IOS = "ios"
    ANDROID = "android"


class AppVersionBase(BaseModel):
    """앱 버전 기본 스키마"""

    version_name: str = Field(..., description="버전명 (예: 1.0.0)")
    platform: PlatformType = Field(..., description="플랫폼")
    description: str | None = Field(None, description="버전 설명 및 변경사항")
    is_mandatory: bool = Field(False, description="필수 업데이트 여부")


class AppVersionCreate(AppVersionBase):
    """앱 버전 생성 스키마"""

    pass


class AppVersionUpdate(BaseModel):
    """앱 버전 업데이트 스키마"""

    description: str | None = None
    is_mandatory: bool | None = None
    is_active: bool | None = None


class UploadAppRequest(BaseModel):
    version_name: str
    platform: PlatformType
    file: UploadFile
    description: str | None = None
    is_mandatory: bool = False


class UploadAppResponseData(AppVersionBase):
    """앱 버전 응답 스키마"""

    model_config = {"from_attributes": True}

    id: UUID
    file_path: str
    file_size: int | None
    file_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    download_url: str | None = Field(None, description="다운로드 URL")


class UploadAppResponse(BaseResponse[UploadAppResponseData]):
    pass


class CheckAppVersionRequest(BaseModel):
    """앱 버전 체크 요청 스키마"""

    current_version: str = Field(..., description="현재 앱 버전")
    platform: PlatformType = Field(..., description="플랫폼")


class CheckAppVersionResponseData(BaseModel):
    """앱 버전 체크 응답 스키마"""

    has_update: bool = Field(..., description="업데이트 가능 여부")
    is_mandatory: bool = Field(False, description="필수 업데이트 여부")
    latest_version: UploadAppResponseData | None = Field(
        None, description="최신 버전 정보"
    )
    message: str | None = Field(None, description="안내 메시지")


class CheckAppVersionResponse(BaseResponse[CheckAppVersionResponseData]):
    pass
