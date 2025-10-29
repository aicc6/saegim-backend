"""
인증 관리 API 라우터
로그인, 로그아웃, 토큰 갱신, 사용자 정보 조회
"""

import logging
from typing import Optional
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    File,
    UploadFile,
    status,
)
from app.core.config import get_settings
from app.core.deps import (
    AuthServiceDep,
    CurrentUser,
    CurrentUserId,
    get_current_user,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ResetPasswordResponse,
    RestoreAccountResponse,
    SendEmailChangeVerificationRequest,
    SendPasswordResetEmailResponse,
    SendRestoreEmailResponse,
    VerifyPasswordAndChangeEmailRequest,
    GetCurrentUserInfoResponse,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    SendPasswordResetEmailRequest,
    SendEmailChangeVerificationResponse,
    UpdateUserProfileRequest,
    RefreshTokenResponse,
    ResetPasswordRequest,
    RestoreAccountRequest,
    SendRestoreEmailRequest,
    UpdateUserProfileResponse,
    UpdateUserSettingsRequest,
    UpdateUserSettingsResponse,
    UploadProfileImageResponse,
    VerifyEmailChangeTokenResponse,
    VerifyPasswordAndChangeEmailResponse,
    VerifyPasswordRequest,
    VerifyPasswordResetCodeRequest,
    VerifyPasswordResetCodeResponse,
    VerifyPasswordResponse,
    WithdrawAccountResponse,
    WithdrawRequest,
)
from app.utils.cookie import CookieUtils
from app.utils.i18n import translate


router = APIRouter(tags=["Authentication"])

# 인증이 필요한 라우터
authenticated_router = APIRouter(
    tags=["Authentication"],
    dependencies=[Depends(get_current_user)],
)

settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse)
async def login(
    auth_service: AuthServiceDep,
    payload: LoginRequest,
    response: Response,
    http_request: Request,
):
    """이메일 로그인 API"""
    data, access_token, refresh_token = auth_service.login(payload)

    # 쿠키에 토큰 설정 (환경별 동적 설정)
    CookieUtils.set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        data=data,
        message=translate(
            "auth.login_success",
            http_request,
            default="로그인이 성공적으로 완료되었습니다.",
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    response: Response,
    http_request: Request,
    current_user: CurrentUser,
):
    """로그아웃 API - 구글 OAuth 세션 정리, JWT 토큰 무효화, 쿠키 정리"""
    data = await auth_service.logout(current_user_id)

    CookieUtils.clear_auth_cookies(response)

    return LogoutResponse(
        data=data,
        message=translate(
            "auth.logout_success",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="로그아웃이 완료되었습니다",
        ),
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    auth_service: AuthServiceDep,
    response: Response,
    http_request: Request,
    refresh_token: Optional[str] = Cookie(None),
):
    """JWT 토큰 갱신 API - Refresh Token을 사용하여 새로운 Access Token 발급"""
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token이 필요합니다.",
        )

    data, access_token, new_refresh_token = auth_service.refresh_token(refresh_token)

    CookieUtils.set_auth_cookies(response, access_token, new_refresh_token)

    return RefreshTokenResponse(
        data=data,
        message=translate(
            "auth.refresh_success",
            http_request,
            default="토큰이 성공적으로 갱신되었습니다.",
        ),
    )


@authenticated_router.get("/me", response_model=GetCurrentUserInfoResponse)
async def get_current_user_info(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    http_request: Request,
    current_user: CurrentUser,
):
    """현재 로그인한 사용자 정보 조회 API"""
    data = auth_service.get_current_user_info(current_user_id)

    return GetCurrentUserInfoResponse(
        data=data,
        message=translate(
            "auth.me_success",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="현재 사용자 정보를 성공적으로 조회했습니다.",
        ),
    )


@authenticated_router.put("/profile", response_model=UpdateUserProfileResponse)
async def update_user_profile(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    request: UpdateUserProfileRequest,
    http_request: Request,
    current_user: CurrentUser,
):
    """사용자 프로필 업데이트 API"""
    data = auth_service.update_user_profile(current_user_id, request)

    return UpdateUserProfileResponse(
        data=data,
        message=translate(
            "auth.profile_update_success",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="프로필이 성공적으로 업데이트되었습니다.",
        ),
    )


@authenticated_router.patch("/me/settings", response_model=UpdateUserSettingsResponse)
async def update_user_settings(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    payload: UpdateUserSettingsRequest,
    http_request: Request,
    current_user: CurrentUser,
):
    """사용자 설정 업데이트 API"""
    data = auth_service.update_user_settings(current_user_id, payload)

    preferred_language = (
        data.preferred_language.value
        if data.preferred_language is not None
        else current_user.preferred_language
    )

    return UpdateUserSettingsResponse(
        data=data,
        message=translate(
            "auth.settings_update_success",
            http_request,
            user_preferred_language=preferred_language,
            default="사용자 설정이 성공적으로 업데이트되었습니다.",
        ),
    )


# === 프로필 이미지 업로드 엔드포인트 ===
@authenticated_router.post(
    "/profile/upload-image",
    response_model=UploadProfileImageResponse,
)
async def upload_profile_image(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    http_request: Request,
    current_user: CurrentUser,
    *,
    image: UploadFile = File(description="프로필 이미지 파일"),
):
    """프로필 이미지 업로드 API"""
    data = await auth_service.upload_profile_image(current_user_id, image)

    return UploadProfileImageResponse(
        data=data,
        message=translate(
            "auth.profile_image_upload_success",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="프로필 이미지가 성공적으로 업로드되었습니다.",
        ),
    )


# === 이메일 변경 관련 엔드포인트 ===
@authenticated_router.post(
    "/change-email/send-verification",
    response_model=SendEmailChangeVerificationResponse,
)
async def send_email_change_verification(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    request: SendEmailChangeVerificationRequest,
    http_request: Request,
    current_user: CurrentUser,
):
    """이메일 변경을 위한 인증 URL 발송 API"""
    data = await auth_service.send_email_change_verification(
        current_user_id, request.new_email
    )

    return SendEmailChangeVerificationResponse(
        data=data,
        message=translate(
            "auth.email_change_verification_sent",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="이메일 변경 인증 이메일이 성공적으로 발송되었습니다.",
        ),
    )


@router.get("/change-email/verify-token", response_model=VerifyEmailChangeTokenResponse)
async def verify_email_change_token(
    auth_service: AuthServiceDep,
    token: str,
    http_request: Request,
    email: Optional[str] = None,
):
    """이메일 변경 토큰 검증 API"""
    data = auth_service.verify_email_change_token(token, email)

    return VerifyEmailChangeTokenResponse(
        data=data,
        message=translate(
            "auth.email_change_token_verified",
            http_request,
            default="토큰 검증 성공",
        ),
    )


@authenticated_router.post(
    "/change-email/verify-password",
    response_model=VerifyPasswordAndChangeEmailResponse,
)
async def verify_password_and_change_email(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    request: VerifyPasswordAndChangeEmailRequest,
    http_request: Request,
    current_user: CurrentUser,
):
    """토큰 검증 및 비밀번호 확인 후 이메일 변경 API"""
    data = auth_service.verify_password_and_change_email(current_user_id, request)

    return VerifyPasswordAndChangeEmailResponse(
        data=data,
        message=translate(
            "auth.email_change_completed",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="이메일 변경이 완료되었습니다. 보안을 위해 다시 로그인해주세요.",
        ),
    )


# === 계정 탈퇴 관련 엔드포인트 ===
@authenticated_router.post("/withdraw", response_model=WithdrawAccountResponse)
async def withdraw_account(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    request: WithdrawRequest,
    response: Response,
    http_request: Request,
    current_user: CurrentUser,
):
    """회원 탈퇴 API"""
    data = auth_service.withdraw_account(current_user_id, request)

    CookieUtils.clear_auth_cookies(response)

    return WithdrawAccountResponse(
        data=data,
        message=translate(
            "auth.account_withdrawn",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="계정 탈퇴가 성공적으로 처리되었습니다.",
        ),
    )


# =============================================================================
# 비밀번호 재설정 관련 엔드포인트
# =============================================================================
@router.post(
    "/forgot-password",
    response_model=SendPasswordResetEmailResponse,
)
async def send_password_reset_email(
    auth_service: AuthServiceDep,
    request: SendPasswordResetEmailRequest,
    http_request: Request,
):
    """
    비밀번호 재설정 이메일 발송

    Args:
        request: 이메일 주소
        db: 데이터베이스 세션

    Returns:
        발송 결과
    """
    data = await auth_service.send_password_reset_email(request)

    return SendPasswordResetEmailResponse(
        data=data,
        message=translate(
            "auth.password_reset_email_sent",
            http_request,
            default="비밀번호 재설정 이메일을 발송했습니다.",
        ),
    )


@router.post("/forgot-password/verify", response_model=VerifyPasswordResetCodeResponse)
async def verify_password_reset_code(
    auth_service: AuthServiceDep,
    request: VerifyPasswordResetCodeRequest,
    http_request: Request,
):
    """
    비밀번호 재설정 인증코드 확인

    Args:
        request: 이메일과 인증코드
        db: 데이터베이스 세션

    Returns:
        인증 결과
    """
    data = auth_service.verify_password_reset_code(request)

    return VerifyPasswordResetCodeResponse(
        data=data,
        message=translate(
            "auth.password_reset_code_verified",
            http_request,
            default="인증코드가 확인되었습니다.",
        ),
    )


@router.post("/forgot-password/reset", response_model=ResetPasswordResponse)
async def reset_password(
    auth_service: AuthServiceDep,
    request: ResetPasswordRequest,
    http_request: Request,
):
    """
    비밀번호 재설정

    Args:
        request: 이메일, 인증코드, 새 비밀번호
        db: 데이터베이스 세션

    Returns:
        재설정 결과
    """
    data = auth_service.reset_password(request)

    return ResetPasswordResponse(
        data=data,
        message=translate(
            "auth.password_reset_success",
            http_request,
            default="비밀번호가 성공적으로 변경되었습니다.",
        ),
    )


# =============================================================================
# 비밀번호 변경 관련 엔드포인트
# =============================================================================
@authenticated_router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
)
async def change_password(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserId,
    request: ChangePasswordRequest,
    http_request: Request,
    current_user: CurrentUser,
):
    """
    비밀번호 변경

    Args:
        request: 현재 비밀번호와 새 비밀번호
        current_user: 현재 사용자
        db: 데이터베이스 세션

    Returns:
        변경 결과
    """
    data = auth_service.change_password(current_user_id, request)

    return ChangePasswordResponse(
        data=data,
        message=translate(
            "auth.password_reset_success",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="비밀번호가 성공적으로 변경되었습니다.",
        ),
    )


@authenticated_router.post(
    "/verify-password",
    response_model=VerifyPasswordResponse,
)
async def verify_password(
    auth_service: AuthServiceDep,
    current_user: CurrentUser,
    request: VerifyPasswordRequest,
    http_request: Request,
):
    """
    현재 비밀번호 확인

    Args:
        current_user: 현재 사용자
        request: 현재 비밀번호

    Returns:
        비밀번호 확인 결과
    """
    data = auth_service.verify_password(current_user, request)

    return VerifyPasswordResponse(
        data=data,
        message=translate(
            "auth.password_verified",
            http_request,
            user_preferred_language=current_user.preferred_language,
            default="비밀번호가 정상적으로 확인되었습니다.",
        ),
    )


# =============================================================================
# 계정 복구 관련 엔드포인트
# =============================================================================


@router.post(
    "/restore/send-restore-email",
    response_model=SendRestoreEmailResponse,
)
async def send_restore_email(
    auth_service: AuthServiceDep,
    request: SendRestoreEmailRequest,
    http_request: Request,
):
    """
    복구 이메일 발송 API

    Args:
        request: 복구 이메일 발송 요청 데이터

    Returns:
        이메일 발송 성공 응답
    """
    data = await auth_service.send_restore_email(request)

    return SendRestoreEmailResponse(
        data=data,
        message=translate(
            "auth.restore_email_sent",
            http_request,
            default="복구 이메일이 성공적으로 발송되었습니다.",
        ),
    )


@router.post(
    "/restore",
    response_model=RestoreAccountResponse,
)
async def restore_account(
    auth_service: AuthServiceDep,
    request: RestoreAccountRequest,
    http_request: Request,
):
    """
    계정 복구 API

    Args:
        request: 복구 요청 데이터 (이메일, 인증코드)
        db: 데이터베이스 세션

    Returns:
        복구 성공 응답
    """
    data = auth_service.restore_account(request)

    return RestoreAccountResponse(
        data=data,
        message=translate(
            "auth.account_restored",
            http_request,
            default="계정이 복구되었습니다.",
        ),
    )


@router.post("/google-login", response_model=LoginResponse)
async def google_login_with_id_token(
    auth_service: AuthServiceDep,
    payload: GoogleLoginRequest,
    response: Response,
    http_request: Request,
):
    """Google ID 토큰을 이용한 모바일 로그인 엔드포인트"""
    data, access_token, refresh_token = await auth_service.google_login_with_id_token(
        payload
    )

    CookieUtils.set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        data=data,
        message=translate(
            "auth.google_login_success",
            http_request,
            default="구글 로그인이 성공적으로 완료되었습니다.",
        ),
    )
