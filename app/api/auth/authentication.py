"""
인증 관리 API 라우터
로그인, 로그아웃, 토큰 갱신, 사용자 정보 조회
"""

import string
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
    File,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlalchemy import select, update, delete
from app.constants import AccountType, OAuthProvider
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.models.diary import DiaryEntry
from app.models.email_verification import EmailVerification
from app.models.fcm import FCMToken, NotificationHistory, NotificationSettings
from app.models.notification import Notification
from app.models.oauth_token import OAuthToken
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailChangeWithTokenRequest,
    EmailVerificationRequest,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponse,
    PasswordResetEmailRequest,
    PasswordResetEmailResponse,
    ProfileUpdateRequest,
    ResetPasswordRequest,
    RestoreRequest,
    RestoreResponse,
    SendRestoreEmailRequest,
    VerifyPasswordRequest,
    VerifyPasswordResetCodeRequest,
    WithdrawRequest,
)
from app.schemas.base import BaseResponse
from app.services.logout_service import LogoutService
from app.utils.email_service import EmailService
from app.utils.encryption import password_hasher
from app.utils.minio_upload import upload_image_with_thumbnail_to_minio
from app.utils.validators import validate_image_file

from app.services.google_id_token_service import GoogleIdTokenService


router = APIRouter(tags=["Authentication"])

# 인증이 필요한 라우터
authenticated_router = APIRouter(
    tags=["Authentication"],
    dependencies=[Depends(get_current_user)],
)

settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=BaseResponse[LoginResponse])
async def login(
    db: DbSession,
    request: LoginRequest,
):
    """이메일 로그인 API"""
    try:
        # 1. 사용자 조회 (Soft Delete 포함)
        stmt = select(User).where(User.email == request.email)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        # 2. Soft Delete된 계정인지 확인
        if user.deleted_at is not None:
            current_time = (
                datetime.now(user.deleted_at.tzinfo)
                if user.deleted_at.tzinfo
                else datetime.now()
            )
            deleted_time = (
                user.deleted_at.replace(tzinfo=None)
                if user.deleted_at.tzinfo
                else user.deleted_at
            )
            current_time_naive = (
                current_time.replace(tzinfo=None)
                if current_time.tzinfo
                else current_time
            )

            # 30일 이내인지 확인
            if deleted_time >= current_time_naive - timedelta(days=30):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ACCOUNT_DELETED",
                        "message": "탈퇴된 계정입니다. 30일 이내에 복구할 수 있습니다.",
                        "deleted_at": user.deleted_at.isoformat(),
                        "restore_available": True,
                        "days_remaining": 30 - (current_time_naive - deleted_time).days,
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ACCOUNT_PERMANENTLY_DELETED",
                        "message": "탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                        "deleted_at": user.deleted_at.isoformat(),
                        "restore_available": False,
                    },
                )

        # 3. 이메일 회원가입 사용자인지 확인
        if user.account_type != AccountType.EMAIL.value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="소셜 로그인으로 가입된 계정입니다.",
            )

        # 4. 비밀번호 검증
        if not password_hasher.verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        # 5. 계정 활성화 상태 확인
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="비활성화된 계정입니다.",
            )

        # 6. JWT 토큰 생성
        access_token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        # 7. 응답 생성 (쿠키만 설정, 응답에는 토큰 제외)
        response_data = LoginResponse(
            user_id=str(user.id),
            email=user.email,
            nickname=user.nickname,
            message="로그인이 완료되었습니다.",
        )

        logger.info(f"사용자 로그인: {user.email}")

        # 쿠키 설정을 위한 응답 생성
        response = JSONResponse(
            content={
                "success": True,
                "message": "로그인이 성공적으로 완료되었습니다.",
                "data": response_data.model_dump(),
            }
        )

        # 쿠키에 토큰 설정 (환경별 동적 설정)
        _set_auth_cookies(response, access_token, refresh_token)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"로그인 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로그인 중 오류가 발생했습니다.",
        )


@router.post("/logout", response_model=BaseResponse[dict[str, Any]])
async def logout(
    db: DbSession,
    request: Request,
    response: Response,
):
    """로그아웃 API - 구글 OAuth 세션 정리, JWT 토큰 무효화, 쿠키 정리"""
    logout_service = LogoutService(db)
    success = True
    error_details = []
    current_user_id = None
    user = None

    try:
        # 1. Authorization 헤더에서 토큰 추출 및 사용자 ID 파싱
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

            try:
                # 토큰 페이로드에서 사용자 ID 추출
                payload = decode_access_token(token)
                current_user_id = int(payload.get("sub"))
                jti = payload.get("jti")

                # 사용자 정보 조회
                stmt = select(User).where(User.id == current_user_id)
                result = db.execute(stmt)
                user = result.scalar_one_or_none()

                if jti:
                    logger.info(f"Token logout requested: {jti}")

            except Exception as e:
                logger.warning(f"Failed to decode token: {e}")

        # 2. 구글 OAuth 세션 정리
        if (
            user
            and user.account_type == AccountType.SOCIAL.value
            and user.provider == OAuthProvider.GOOGLE.value
        ):
            stmt = select(OAuthToken).where(
                OAuthToken.user_id == current_user_id,
                OAuthToken.provider == OAuthProvider.GOOGLE.value,
            )
            result = db.execute(stmt)
            oauth_token = result.scalar_one_or_none()

            if oauth_token and oauth_token.access_token:
                if not await logout_service.revoke_google_token(
                    oauth_token.access_token
                ):
                    error_details.append("Google token revocation failed")
                    success = False

        # 3. OAuth 토큰 무효화
        if current_user_id:
            logout_service.invalidate_oauth_tokens(str(current_user_id))

        # 4. 쿠키 정리
        _clear_auth_cookies(response)

        # 5. 보안 로그 기록
        if current_user_id:
            logout_service.log_logout_attempt(
                str(current_user_id),
                success,
                ", ".join(error_details) if error_details else "",
            )

        return BaseResponse(
            data={
                "logout_time": datetime.now(timezone.utc).isoformat(),
                "user_id": str(current_user_id) if current_user_id else None,
                "account_type": user.account_type if user else None,
                "provider": (
                    user.provider
                    if user and user.account_type == AccountType.SOCIAL.value
                    else None
                ),
                "errors": error_details if error_details else None,
            },
            message=(
                "로그아웃이 완료되었습니다"
                if success
                else "로그아웃이 완료되었습니다 (구글 세션 정리 실패)"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}")
        if current_user_id:
            logout_service.log_logout_attempt(str(current_user_id), False, str(e))

        return BaseResponse(
            data={
                "logout_time": datetime.now(timezone.utc).isoformat(),
                "user_id": str(current_user_id) if current_user_id else None,
                "account_type": "unknown",
                "provider": None,
                "errors": ["Unexpected error occurred"],
            },
            message="로그아웃이 완료되었습니다",
        )


@router.post("/refresh", response_model=BaseResponse[dict[str, Any]])
async def refresh_token(
    db: DbSession,
    request: Request,
):
    """JWT 토큰 갱신 API - Refresh Token을 사용하여 새로운 Access Token 발급"""
    try:
        # 1. 쿠키에서 Refresh Token 추출
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token이 필요합니다.",
            )

        # 2. Refresh Token 검증
        try:
            payload = decode_refresh_token(refresh_token)
            user_id = payload.get("sub")
            token_type = payload.get("type")

            if token_type != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="유효하지 않은 토큰 타입입니다.",
                )

        except Exception as e:
            logger.warning(f"Refresh token 검증 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 refresh token입니다.",
            )

        # 3. 사용자 정보 조회
        stmt = select(User).where(User.id == user_id)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자를 찾을 수 없습니다.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="비활성화된 계정입니다.",
            )

        # 4. 새로운 토큰 발급
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        new_refresh_token = create_refresh_token(data={"sub": str(user.id)})

        logger.info(f"토큰 갱신 성공: {user.email}")

        # 5. 쿠키에 새로운 토큰 설정
        response = JSONResponse(
            content={
                "success": True,
                "message": "토큰이 성공적으로 갱신되었습니다.",
                "data": {
                    "user_id": str(user.id),
                    "email": user.email,
                    "nickname": user.nickname,
                },
            }
        )

        _set_auth_cookies(response, access_token, new_refresh_token)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 갱신 중 오류 발생: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 중 오류가 발생했습니다.",
        )


@authenticated_router.get("/me", response_model=BaseResponse[dict[str, Any]])
async def get_current_user_info(
    db: DbSession,
    current_user: CurrentUser,
):
    """현재 로그인한 사용자 정보 조회 API"""
    try:
        user_data = {
            "user_id": str(current_user.id),
            "email": current_user.email,
            "nickname": current_user.nickname,
            "profile_image_url": current_user.profile_image_url,
            "account_type": current_user.account_type,
            "provider": current_user.provider,
            "is_active": current_user.is_active,
            "created_at": (
                current_user.created_at.isoformat() if current_user.created_at else None
            ),
        }

        return BaseResponse(
            data=user_data, message="현재 사용자 정보를 성공적으로 조회했습니다."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 정보 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 정보 조회 중 오류가 발생했습니다.",
        )


@authenticated_router.put("/profile", response_model=BaseResponse[dict[str, Any]])
async def update_user_profile(
    db: DbSession,
    current_user: CurrentUser,
    request: ProfileUpdateRequest,
):
    """사용자 프로필 업데이트 API"""
    try:
        # 닉네임 업데이트
        current_user.nickname = request.nickname

        # 프로필 이미지 URL 업데이트 (제공된 경우)
        if request.profile_image_url is not None:
            current_user.profile_image_url = request.profile_image_url

        current_user.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(current_user)

        logger.info(f"프로필 업데이트 성공: {current_user.email} -> {request.nickname}")

        return BaseResponse(
            data={
                "user_id": str(current_user.id),
                "nickname": current_user.nickname,
                "profile_image_url": current_user.profile_image_url,
                "updated_at": current_user.updated_at.isoformat(),
            },
            message="프로필이 성공적으로 업데이트되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"프로필 업데이트 실패: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로필 업데이트 중 오류가 발생했습니다.",
        )


# === 프로필 이미지 업로드 엔드포인트 ===
@authenticated_router.post(
    "/profile/upload-image", response_model=BaseResponse[dict[str, Any]]
)
async def upload_profile_image(
    db: DbSession,
    current_user: CurrentUser,
    *,
    image: UploadFile = File(description="프로필 이미지 파일"),
):
    """프로필 이미지 업로드 API"""
    try:
        # 이미지 파일 검증
        validate_image_file(image.content_type, image.size)

        # MinIO에 이미지와 썸네일 업로드
        file_id, _original_url, thumbnail_url = (
            await upload_image_with_thumbnail_to_minio(image)
        )

        # 사용자 프로필에 이미지 URL 저장 (썸네일 사용)
        current_user.profile_image_url = thumbnail_url
        current_user.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(current_user)

        logger.info(
            f"프로필 이미지 업로드 성공: {current_user.email} -> {thumbnail_url}"
        )

        return BaseResponse(
            data={
                "image_url": thumbnail_url,
                "file_id": file_id,
                "user_id": str(current_user.id),
                "updated_at": current_user.updated_at.isoformat(),
            },
            message="프로필 이미지가 성공적으로 업로드되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"프로필 이미지 업로드 실패: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로필 이미지 업로드 중 오류가 발생했습니다.",
        )


# === 이메일 변경 관련 엔드포인트 ===
@authenticated_router.post(
    "/change-email/send-verification", response_model=BaseResponse[dict[str, str]]
)
async def send_email_change_verification(
    db: DbSession,
    current_user: CurrentUser,
    request: EmailVerificationRequest,
):
    """이메일 변경을 위한 인증 URL 발송 API"""
    try:

        # 1. 새로운 이메일 중복 확인
        stmt = select(User).where(User.email == request.new_email)
        result = db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 사용 중인 이메일입니다.",
            )

        # 2. 기존 이메일과 같은지 확인
        if request.new_email == current_user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 사용 중인 이메일과 동일합니다.",
            )

        # 3. 인증 토큰 생성
        verification_token = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        # 4. 기존 인증 코드가 있다면 삭제
        stmt = select(EmailVerification).where(
            EmailVerification.email == request.new_email,
            EmailVerification.verification_type == "change",
        )
        result = db.execute(stmt)
        existing_verification = result.scalar_one_or_none()

        if existing_verification:
            db.delete(existing_verification)

        # 5. 새로운 인증 토큰 저장
        new_verification = EmailVerification(
            email=request.new_email,
            verification_code=verification_token,
            verification_type="change",
            expires_at=datetime.now() + timedelta(minutes=30),
        )

        db.add(new_verification)
        db.commit()

        # 6. 인증 URL 생성
        verification_url = f"{settings.frontend_url}/profile?token={verification_token}&action=change-email"

        # 7. 실제 이메일 발송
        email_service = EmailService()
        await email_service.send_email_change_verification(
            to_email=request.new_email,
            verification_url=verification_url,
            current_email=current_user.email,
        )

        return BaseResponse(
            data={
                "message": "인증 이메일이 발송되었습니다.",
                "email_sent": "true",
                "target_email": request.new_email,
            },
            message="이메일 변경 인증 이메일이 성공적으로 발송되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"이메일 변경 인증 URL 발송 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="인증 이메일 발송 중 오류가 발생했습니다.",
        )


@router.get("/change-email/verify-token")
async def verify_email_change_token(
    db: DbSession,
    token: str,
    email: str | None = None,
):
    """이메일 변경 토큰 검증 API"""
    try:

        # 1. 토큰 검증
        if email:
            stmt = select(EmailVerification).where(
                EmailVerification.email == email,
                EmailVerification.verification_code == token,
                EmailVerification.verification_type == "change",
                EmailVerification.expires_at > datetime.now(),
                EmailVerification.is_used.is_(False),
            )
        else:
            stmt = select(EmailVerification).where(
                EmailVerification.verification_code == token,
                EmailVerification.verification_type == "change",
                EmailVerification.expires_at > datetime.now(),
                EmailVerification.is_used.is_(False),
            )

        result = db.execute(stmt)
        verification = result.scalar_one_or_none()

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 인증 토큰입니다.",
            )

        return BaseResponse(
            data={
                "valid": "true",
                "email": verification.email,
                "message": "인증 토큰이 유효합니다.",
            },
            message="토큰 검증 성공",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 검증 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="토큰 검증 중 오류가 발생했습니다.",
        )


@authenticated_router.post(
    "/change-email/verify-password", response_model=BaseResponse[dict[str, str]]
)
async def verify_password_and_change_email(
    db: DbSession,
    current_user: CurrentUser,
    request: EmailChangeWithTokenRequest,
):
    """토큰 검증 및 비밀번호 확인 후 이메일 변경 API"""
    try:

        # 1. 이메일 회원가입 사용자인지 확인
        if current_user.account_type != AccountType.EMAIL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 로그인 사용자는 비밀번호 확인이 필요하지 않습니다.",
            )

        # 2. 토큰 검증
        stmt = select(EmailVerification).where(
            EmailVerification.email == request.new_email,
            EmailVerification.verification_code == request.token,
            EmailVerification.verification_type == "change",
            EmailVerification.expires_at > datetime.now(),
            EmailVerification.is_used.is_(False),
        )
        result = db.execute(stmt)
        verification = result.scalar_one_or_none()

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 인증 토큰입니다.",
            )

        # 3. 비밀번호 검증
        if not password_hasher.verify_password(
            request.password, current_user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="비밀번호가 올바르지 않습니다.",
            )

        # 4. 새로운 이메일 중복 확인
        stmt = select(User).where(User.email == request.new_email)
        result = db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 사용 중인 이메일입니다.",
            )

        # 5. 이메일 변경
        old_email = current_user.email
        current_user.email = request.new_email

        # 6. 토큰 사용 처리
        verification.is_used = True

        db.commit()

        logger.info(f"이메일 변경 성공: {old_email} → {request.new_email}")

        return BaseResponse(
            data={
                "message": "이메일이 성공적으로 변경되었습니다.",
                "email_changed": "true",
                "old_email": old_email,
                "new_email": request.new_email,
                "requires_logout": "true",
            },
            message="이메일 변경이 완료되었습니다. 보안을 위해 다시 로그인해주세요.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"이메일 변경 실패: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 변경 중 오류가 발생했습니다.",
        )


# === 계정 탈퇴 관련 엔드포인트 ===
@authenticated_router.post("/withdraw", response_model=BaseResponse[dict[str, Any]])
async def withdraw_account(
    db: DbSession,
    current_user: CurrentUser,
    request: WithdrawRequest,
    response: Response,
):
    """회원 탈퇴 API"""
    try:

        logger.info(f"탈퇴 요청 시작: {current_user.id}")

        # 1. 계정 타입별 비밀번호 확인
        if current_user.account_type == AccountType.EMAIL.value:
            if not request.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="이메일 계정은 비밀번호 확인이 필요합니다.",
                )
            if not password_hasher.verify_password(
                request.password, current_user.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="비밀번호가 올바르지 않습니다.",
                )

        # 2. 탈퇴 처리
        withdrawal_date = datetime.now(timezone.utc)

        # 3. User 테이블 Soft Delete
        db.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(deleted_at=withdrawal_date)
        )

        # 4. Diary 테이블 Soft Delete
        db.execute(
            update(DiaryEntry)
            .where(DiaryEntry.user_id == current_user.id)
            .values(deleted_at=withdrawal_date)
        )

        # 5. 관련 데이터 Hard Delete
        db.execute(delete(FCMToken).where(FCMToken.user_id == current_user.id))
        db.execute(
            delete(NotificationSettings).where(
                NotificationSettings.user_id == current_user.id
            )
        )
        db.execute(
            delete(NotificationHistory).where(
                NotificationHistory.user_id == current_user.id
            )
        )
        db.execute(delete(Notification).where(Notification.user_id == current_user.id))
        db.execute(delete(OAuthToken).where(OAuthToken.user_id == current_user.id))
        db.execute(
            delete(EmailVerification).where(
                EmailVerification.email == current_user.email
            )
        )

        db.commit()

        # 6. 쿠키 무효화
        _clear_auth_cookies(response)

        logger.info(f"탈퇴 성공: {current_user.id}")

        return BaseResponse(
            data={
                "message": "계정 탈퇴가 완료되었습니다.",
                "withdrawal_date": withdrawal_date.isoformat(),
                "restore_until": (withdrawal_date + timedelta(days=30)).isoformat(),
                "success": True,
            },
            message="계정 탈퇴가 성공적으로 처리되었습니다.",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"탈퇴 처리 중 예외 발생: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="탈퇴 처리 중 오류가 발생했습니다.",
        )


def _set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str):
    """인증 쿠키 설정"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        domain=settings.cookie_domain,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_auth_cookies(response: Response):
    """인증 쿠키 삭제"""
    for key in ["access_token", "refresh_token", "session"]:
        response.delete_cookie(
            key=key,
            path="/",
            secure=settings.cookie_secure,
            httponly=settings.cookie_httponly,
            samesite=settings.cookie_samesite,
            domain=settings.cookie_domain,
        )


# =============================================================================
# 비밀번호 재설정 관련 엔드포인트
# =============================================================================


@router.post(
    "/forgot-password", response_model=BaseResponse[PasswordResetEmailResponse]
)
async def send_password_reset_email(
    db: DbSession,
    request: PasswordResetEmailRequest,
):
    """
    비밀번호 재설정 이메일 발송

    Args:
        request: 이메일 주소
        db: 데이터베이스 세션

    Returns:
        발송 결과
    """
    try:
        # 사용자 조회
        stmt = select(User).where(User.email == request.email)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return BaseResponse(
                success=False,
                data=PasswordResetEmailResponse(
                    success=False,
                    message="해당 이메일로 가입된 계정이 없습니다.",
                    is_social_account=False,
                    email_sent=False,
                ),
                message="해당 이메일로 가입된 계정이 없습니다.",
            )

        # 소셜 계정 사용자인 경우
        if user.account_type == AccountType.SOCIAL.value:
            provider_name = user.provider or "소셜"
            return BaseResponse(
                success=False,
                data=PasswordResetEmailResponse(
                    success=False,
                    message=f"소셜 계정 사용자입니다. {provider_name} 계정으로 가입된 사용자입니다. 비밀번호 재설정은 해당 서비스에서 직접 진행해주세요.",
                    is_social_account=True,
                    email_sent=False,
                    redirect_to_error_page=True,
                ),
                message=f"소셜 계정 사용자입니다. {provider_name} 계정으로 가입된 사용자입니다.",
            )

        # 이메일 계정 사용자인 경우
        # 기존 토큰이 있다면 만료 처리
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.is_used.is_(False),
        )
        result = db.execute(stmt)
        existing_tokens = result.scalars().all()

        for token in existing_tokens:
            token.is_used = True
            token.used_at = datetime.now(timezone.utc)

        # 새로운 토큰 생성
        token_value = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = PasswordResetToken(
            user_id=user.id, token=token_value, expires_at=expires_at, is_used=False
        )

        db.add(reset_token)
        db.commit()
        db.refresh(reset_token)

        # 비밀번호 재설정 이메일 발송
        email_service = EmailService()
        reset_url = f"{settings.frontend_url}/reset-password?token={token_value}"

        email_sent = await email_service.send_password_reset_email(
            to_email=user.email, nickname=user.nickname, reset_url=reset_url
        )

        if not email_sent:
            return BaseResponse(
                success=False,
                data=PasswordResetEmailResponse(
                    success=False,
                    message="이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.",
                    is_social_account=False,
                    email_sent=False,
                ),
                message="이메일 발송에 실패했습니다.",
            )

        return BaseResponse(
            success=True,
            data=PasswordResetEmailResponse(
                success=True,
                message="비밀번호 재설정 이메일을 발송했습니다.",
                is_social_account=False,
                email_sent=True,
            ),
            message="비밀번호 재설정 이메일을 발송했습니다.",
        )

    except Exception as e:
        db.rollback()
        logger.error(f"비밀번호 재설정 이메일 발송 중 오류: {e}")

        return BaseResponse(
            success=False,
            data=PasswordResetEmailResponse(
                success=False,
                message="이메일 발송 중 오류가 발생했습니다.",
                is_social_account=False,
                email_sent=False,
            ),
            message="이메일 발송 중 오류가 발생했습니다.",
        )


@router.post("/forgot-password/verify", response_model=BaseResponse[dict[str, Any]])
async def verify_password_reset_code(
    db: DbSession,
    request: VerifyPasswordResetCodeRequest,
):
    """
    비밀번호 재설정 인증코드 확인

    Args:
        request: 이메일과 인증코드
        db: 데이터베이스 세션

    Returns:
        인증 결과
    """
    try:
        # 사용자 조회
        stmt = select(User).where(User.email == request.email)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 이메일로 가입된 계정이 없습니다.",
            )

        # 소셜 계정 사용자인 경우
        if user.account_type == AccountType.SOCIAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 계정 사용자는 비밀번호 재설정이 불가능합니다.",
            )

        # 토큰 조회
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token == request.verification_code,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        result = db.execute(stmt)
        token = result.scalar_one_or_none()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 인증코드입니다.",
            )

        return BaseResponse(
            success=True,
            data={"verified": True},
            message="인증코드가 확인되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인증코드 확인 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="인증코드 확인 중 오류가 발생했습니다.",
        )


@router.post("/forgot-password/reset", response_model=BaseResponse[dict[str, str]])
async def reset_password(
    db: DbSession,
    request: ResetPasswordRequest,
):
    """
    비밀번호 재설정

    Args:
        request: 이메일, 인증코드, 새 비밀번호
        db: 데이터베이스 세션

    Returns:
        재설정 결과
    """
    try:
        # 사용자 조회
        stmt = select(User).where(User.email == request.email)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 이메일로 가입된 계정이 없습니다.",
            )

        # 소셜 계정 사용자인 경우
        if user.account_type == AccountType.SOCIAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 계정 사용자는 비밀번호 재설정이 불가능합니다.",
            )

        # 토큰 조회 및 검증
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token == request.verification_code,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        result = db.execute(stmt)
        token = result.scalar_one_or_none()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 인증코드입니다.",
            )

        # 비밀번호 해시화 및 업데이트
        user.password_hash = password_hasher.hash_password(request.new_password)

        # 토큰 사용 처리
        token.is_used = True
        token.used_at = datetime.now(timezone.utc)

        db.commit()

        return BaseResponse(
            success=True,
            data={"message": "비밀번호가 성공적으로 변경되었습니다."},
            message="비밀번호가 성공적으로 변경되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"비밀번호 재설정 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비밀번호 재설정 중 오류가 발생했습니다.",
        )


# =============================================================================
# 비밀번호 변경 관련 엔드포인트
# =============================================================================
@authenticated_router.post(
    "/change-password", response_model=BaseResponse[dict[str, str]]
)
async def change_password(
    db: DbSession,
    current_user: CurrentUser,
    request: ChangePasswordRequest,
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
    try:
        # 소셜 계정 사용자인 경우
        if current_user.account_type == AccountType.SOCIAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 계정 사용자는 비밀번호 변경이 불가능합니다.",
            )

        # 현재 비밀번호 확인
        if not password_hasher.verify_password(
            request.current_password, current_user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )

        # 새 비밀번호 해시화 및 업데이트
        current_user.password_hash = password_hasher.hash_password(request.new_password)
        db.commit()

        return BaseResponse(
            success=True,
            data={"message": "비밀번호가 성공적으로 변경되었습니다."},
            message="비밀번호가 성공적으로 변경되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"비밀번호 변경 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비밀번호 변경 중 오류가 발생했습니다.",
        )


@authenticated_router.post(
    "/verify-password", response_model=BaseResponse[dict[str, str]]
)
async def verify_password(
    current_user: CurrentUser,
    request: VerifyPasswordRequest,
):
    """
    현재 비밀번호 확인

    Args:
        request: 현재 비밀번호
        current_user: 현재 사용자

    Returns:
        비밀번호 확인 결과
    """
    try:

        # 이메일 회원가입 사용자인지 확인
        if current_user.account_type != AccountType.EMAIL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 로그인 사용자는 비밀번호 확인이 불가능합니다.",
            )

        # 현재 비밀번호 확인
        if not password_hasher.verify_password(
            request.current_password, current_user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )

        return BaseResponse.success(
            data={"message": "비밀번호 확인 완료"},
            message="비밀번호가 정상적으로 확인되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"비밀번호 확인 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비밀번호 확인 중 오류가 발생했습니다.",
        )


# =============================================================================
# 계정 복구 관련 엔드포인트
# =============================================================================


@router.post("/restore/send-restore-email", response_model=BaseResponse[dict[str, str]])
async def send_restore_email(
    db: DbSession,
    request: SendRestoreEmailRequest,
):
    """
    복구 이메일 발송 API

    Args:
        request: 복구 이메일 발송 요청 데이터
        db: 데이터베이스 세션

    Returns:
        이메일 발송 성공 응답
    """
    try:
        # 1. 탈퇴된 사용자 확인
        stmt = select(User).where(
            User.email == request.email, User.deleted_at.is_not(None)
        )
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="탈퇴된 계정을 찾을 수 없습니다.",
            )

        # 2. 30일 이내인지 확인
        current_time = (
            datetime.now(user.deleted_at.tzinfo)
            if user.deleted_at.tzinfo
            else datetime.now()
        )
        deleted_time = (
            user.deleted_at.replace(tzinfo=None)
            if user.deleted_at.tzinfo
            else user.deleted_at
        )
        current_time_naive = (
            current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
        )

        if deleted_time < current_time_naive - timedelta(days=30):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
            )

        # 3. 인증 코드 생성 (6자리 숫자)
        verification_code = str(random.randint(100000, 999999))

        # 4. 기존 인증 코드가 있다면 만료 처리
        stmt = select(EmailVerification).where(
            EmailVerification.email == request.email,
            EmailVerification.verification_type == "restore",
            EmailVerification.expires_at > datetime.now(),
        )
        result = db.execute(stmt)
        existing_verification = result.scalar_one_or_none()

        if existing_verification:
            existing_verification.expires_at = datetime.now() - timedelta(seconds=1)
            existing_verification.is_used = True
            db.commit()

        # 5. 새로운 인증 코드 저장
        new_verification = EmailVerification(
            email=request.email,
            verification_code=verification_code,
            verification_type="restore",
            expires_at=datetime.now() + timedelta(minutes=10),
        )

        db.add(new_verification)
        db.commit()

        # 6. 실제 이메일 발송
        email_service = EmailService()
        email_sent = await email_service.send_verification_email(
            request.email, verification_code, "restore"
        )

        if not email_sent:
            # 이메일 발송 실패 시 인증 코드 삭제
            db.delete(new_verification)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="복구 이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.",
            )

        logger.info(
            f"복구 이메일 발송 성공: {request.email} (인증코드: {verification_code})"
        )

        return BaseResponse(
            success=True,
            data={"message": "복구 이메일이 발송되었습니다."},
            message="복구 이메일이 성공적으로 발송되었습니다.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"복구 이메일 발송 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 발송 중 오류가 발생했습니다.",
        )


@router.post("/restore", response_model=BaseResponse[RestoreResponse])
async def restore_account(
    db: DbSession,
    request: RestoreRequest,
):
    """
    계정 복구 API

    Args:
        request: 복구 요청 데이터 (이메일, 인증코드)
        db: 데이터베이스 세션

    Returns:
        복구 성공 응답
    """
    try:
        # 1. 탈퇴된 사용자 조회
        stmt = select(User).where(
            User.email == request.email, User.deleted_at.is_not(None)
        )
        result = db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="탈퇴된 계정을 찾을 수 없습니다.",
            )

        # 2. 30일 이내인지 확인
        current_time = (
            datetime.now(user.deleted_at.tzinfo)
            if user.deleted_at.tzinfo
            else datetime.now()
        )
        deleted_time = (
            user.deleted_at.replace(tzinfo=None)
            if user.deleted_at.tzinfo
            else user.deleted_at
        )
        current_time_naive = (
            current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
        )

        if deleted_time < current_time_naive - timedelta(days=30):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
            )

        # 3. 이메일 인증 코드 확인
        stmt = select(EmailVerification).where(
            EmailVerification.email == request.email,
            EmailVerification.verification_code == request.verification_code,
            EmailVerification.verification_type == "restore",
            EmailVerification.expires_at > datetime.now(),
            EmailVerification.is_used.is_(False),
        )
        result = db.execute(stmt)
        verification = result.scalar_one_or_none()

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 인증 코드입니다.",
            )

        # 4. 인증 코드 사용 처리
        verification.is_used = True
        db.commit()

        # 5. 계정 복구 처리
        restored_at = datetime.now()

        # User 테이블 복구
        db.execute(update(User).where(User.id == user.id).values(deleted_at=None))

        # Diary 테이블 복구
        db.execute(
            update(DiaryEntry)
            .where(DiaryEntry.user_id == user.id)
            .values(deleted_at=None)
        )

        # 6. 사용된 인증 코드 삭제
        db.delete(verification)

        # 7. 변경사항 커밋
        db.commit()

        # 8. 응답 생성
        account_type_message = (
            "이메일 계정"
            if user.account_type == AccountType.EMAIL.value
            else "소셜 계정"
        )
        response_data = RestoreResponse(
            message=f"{account_type_message}이 성공적으로 복구되었습니다.",
            restored_at=restored_at,
            user_id=str(user.id),
            email=user.email,
            nickname=user.nickname,
        )

        logger.info(f"계정 복구 성공: {user.email}")

        return BaseResponse(
            success=True,
            data=response_data,
            message=f"{account_type_message} 복구가 완료되었습니다.",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"계정 복구 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="계정 복구 중 오류가 발생했습니다.",
        )


@router.post("/google-login", response_model=BaseResponse[LoginResponse])
async def google_login_with_id_token(
    db: DbSession,
    request: GoogleLoginRequest,
):
    """Google ID 토큰을 이용한 모바일 로그인 엔드포인트"""

    try:
        service = GoogleIdTokenService(db)
        user = await service.authenticate(request)

        access_token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        response_data = LoginResponse(
            user_id=str(user.id),
            email=user.email,
            nickname=user.nickname,
            message="구글 로그인이 완료되었습니다.",
        )

        response = JSONResponse(
            content={
                "success": True,
                "message": "구글 로그인이 성공적으로 완료되었습니다.",
                "data": response_data.model_dump(),
            }
        )
        _set_auth_cookies(response, access_token, refresh_token)

        return response

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"구글 로그인 처리 중 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="구글 로그인 처리 중 오류가 발생했습니다.",
        )
