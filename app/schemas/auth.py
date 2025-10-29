import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.base import BaseResponse, MessageResponseData


# authentication
class PreferredLanguage(str, Enum):
    KO = "ko"
    EN = "en"
    JA = "ja"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponseData(BaseModel):
    user_id: str
    email: str
    nickname: str
    message: str


class LoginResponse(BaseResponse[LoginResponseData]):
    pass


class LogoutResponseData(BaseModel):
    logout_time: str
    user_id: UUID
    account_type: str | None
    provider: str | None
    errors: list[str]


class LogoutResponse(BaseResponse[LogoutResponseData]):
    pass


class RefreshTokenResponseData(BaseModel):
    user_id: UUID
    email: str
    nickname: str


class RefreshTokenResponse(BaseResponse[RefreshTokenResponseData]):
    pass


class GetCurrentUserInfoResponseData(BaseModel):
    user_id: UUID
    email: str
    nickname: str
    profile_image_url: str | None
    preferred_language: PreferredLanguage | None
    account_type: str | None
    provider: str | None
    is_active: bool
    created_at: str


class GetCurrentUserInfoResponse(BaseResponse[GetCurrentUserInfoResponseData]):
    pass


class UpdateUserProfileRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=50)
    profile_image_url: str | None = Field(None, max_length=500)


class UpdateUserProfileResponseData(BaseModel):
    user_id: UUID
    nickname: str
    profile_image_url: str | None
    updated_at: str


class UpdateUserProfileResponse(BaseResponse[UpdateUserProfileResponseData]):
    pass


class UpdateUserSettingsRequest(BaseModel):
    preferred_language: PreferredLanguage | None = Field(default=None)


class UpdateUserSettingsResponseData(BaseModel):
    user_id: UUID
    preferred_language: PreferredLanguage | None
    updated_at: str


class UpdateUserSettingsResponse(BaseResponse[UpdateUserSettingsResponseData]):
    pass


class UploadProfileImageResponseData(BaseModel):
    image_url: str | None
    file_id: UUID
    user_id: UUID
    updated_at: str


class UploadProfileImageResponse(BaseResponse[UploadProfileImageResponseData]):
    pass


class SendEmailChangeVerificationResponseData(BaseModel):
    message: str
    email_sent: str
    target_email: str


class SendEmailChangeVerificationResponse(
    BaseResponse[SendEmailChangeVerificationResponseData]
):
    pass


class VerifyEmailChangeTokenResponseData(BaseModel):
    valid: str
    email: str
    message: str


class VerifyEmailChangeTokenResponse(
    BaseResponse[VerifyEmailChangeTokenResponseData],
):
    pass


class VerifyPasswordAndChangeEmailResponseData(BaseModel):
    message: str
    email_changed: str
    old_email: str
    new_email: str
    requires_logout: str


class VerifyPasswordAndChangeEmailResponse(
    BaseResponse[VerifyPasswordAndChangeEmailResponseData],
):
    pass


class WithdrawAccountResponseData(BaseModel):
    message: str
    withdrawal_date: str
    restore_until: str
    success: bool


class WithdrawAccountResponse(BaseResponse[WithdrawAccountResponseData]):
    pass


# 비밀번호 재설정 관련 모델
class SendPasswordResetEmailRequest(BaseModel):
    email: EmailStr


class SendPasswordResetEmailResponseData(BaseModel):
    success: bool
    message: str
    is_social_account: bool = False
    email_sent: bool = False
    redirect_to_error_page: bool = False


class SendPasswordResetEmailResponse(
    BaseResponse[SendPasswordResetEmailResponseData],
):
    pass


class VerifyPasswordResetCodeRequest(BaseModel):
    email: EmailStr
    verification_code: str


class VerifyPasswordResetCodeResponseData(BaseModel):
    verified: bool


class VerifyPasswordResetCodeResponse(
    BaseResponse[VerifyPasswordResetCodeResponseData],
):
    pass


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    verification_code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: Any):
        if len(v) < 9:
            raise ValueError("비밀번호는 9자 이상이어야 합니다")

        # 영문, 숫자, 특수문자 포함 검증
        if not re.match(
            r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{9,}$", v
        ):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다")

        return v


class ResetPasswordResponseData(MessageResponseData):
    pass


class ResetPasswordResponse(BaseResponse[ResetPasswordResponseData]):
    pass


# 비밀번호 변경 관련 모델
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("새 비밀번호는 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("새 비밀번호는 유효한 문자열이어야 합니다")

        if len(v) < 9:
            raise ValueError("비밀번호는 9자 이상이어야 합니다")

        # 영문, 숫자, 특수문자 포함 검증
        if not re.match(
            r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{9,}$", v
        ):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다")

        return v

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("현재 비밀번호는 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("현재 비밀번호는 유효한 문자열이어야 합니다")

        return v


class ChangePasswordResponseData(MessageResponseData):
    pass


class ChangePasswordResponse(BaseResponse[ChangePasswordResponseData]):
    pass


class VerifyPasswordResponseData(MessageResponseData):
    pass


class VerifyPasswordResponse(BaseResponse[VerifyPasswordResponseData]):
    pass


class SendRestoreEmailResponseData(MessageResponseData):
    pass


class SendRestoreEmailResponse(BaseResponse[SendRestoreEmailResponseData]):
    pass


# 비밀번호 확인 전용 모델
class VerifyPasswordRequest(BaseModel):
    current_password: str

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("현재 비밀번호는 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("현재 비밀번호는 유효한 문자열이어야 합니다")

        return v


# 계정 복구 관련 모델
class SendRestoreEmailRequest(BaseModel):
    email: str


class RestoreAccountRequest(BaseModel):
    email: str
    verification_code: str


class RestoreAccountResponseData(BaseModel):
    message: str
    restored_at: datetime
    user_id: str
    email: str
    nickname: str


class RestoreAccountResponse(BaseResponse[RestoreAccountResponseData]):
    pass


class SendEmailChangeVerificationRequest(BaseModel):
    new_email: EmailStr


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class VerifyPasswordAndChangeEmailRequest(BaseModel):
    new_email: EmailStr
    password: str  # 기존 이메일 인증을 위한 비밀번호
    token: str  # 이메일 인증 토큰


class WithdrawRequest(BaseModel):
    password: str  # 이메일 계정의 경우 비밀번호 확인
    reason: str = "기타"  # 탈퇴 이유
    detailed_reason: str | None = None  # 상세 이유


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=10)
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=100)
    photo_url: str | None = Field(default=None, max_length=500)

    @field_validator("id_token")
    @classmethod
    def validate_id_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("유효한 Google ID 토큰이 필요합니다.")
        return value


# registration
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("비밀번호는 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("비밀번호는 유효한 문자열이어야 합니다")

        if len(v) < 9:
            raise ValueError("비밀번호는 9자 이상이어야 합니다")

        # 영문, 숫자, 특수문자 포함 검사
        has_letter = bool(re.search(r"[a-zA-Z]", v))
        has_number = bool(re.search(r"\d", v))
        has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?]', v))

        if not (has_letter and has_number and has_special):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 모두 포함해야 합니다")

        return v

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("닉네임은 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("닉네임은 유효한 문자열이어야 합니다")

        if len(v) < 2 or len(v) > 10:
            raise ValueError("닉네임은 2-10자 사이여야 합니다")

        if not re.match(r"^[가-힣a-zA-Z]+$", v):
            raise ValueError("닉네임은 한글과 영문만 사용 가능합니다")

        return v


class SignUpResponseData(BaseModel):
    user_id: str
    email: str
    nickname: str
    message: str


class SignUpResponse(BaseResponse[SignUpResponseData]):
    pass


class EmailVerificationConfirmRequest(BaseModel):
    email: EmailStr
    verification_code: str
