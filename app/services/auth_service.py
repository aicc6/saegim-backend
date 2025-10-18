import logging
import random
import string
from datetime import UTC, datetime, timedelta
from random import randint
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.constants import AccountType, OAuthProvider
from app.core.config import get_settings
from app.core.security import (
    JWTHandler,
)
from app.core.transaction_manager import TransactionManager
from app.exceptions.auth import (
    DuplicateEmailException,
    DuplicateNicknameException,
    MismatchedVerificationCodeException,
    NeedVerifyEmailException,
    SendVerificationEmailException,
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
    ChangePasswordResponseData,
    EmailVerificationConfirmRequest,
    EmailVerificationRequest,
    GetCurrentUserInfoResponseData,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponseData,
    LogoutResponseData,
    RefreshTokenResponseData,
    ResetPasswordRequest,
    ResetPasswordResponseData,
    RestoreAccountRequest,
    RestoreAccountResponseData,
    SendEmailChangeVerificationResponseData,
    SendPasswordResetEmailRequest,
    SendPasswordResetEmailResponseData,
    SendRestoreEmailRequest,
    SendRestoreEmailResponseData,
    SignupRequest,
    SignUpResponseData,
    UpdateUserProfileRequest,
    UpdateUserProfileResponseData,
    UploadProfileImageResponseData,
    VerifyEmailChangeTokenResponseData,
    VerifyPasswordAndChangeEmailRequest,
    VerifyPasswordAndChangeEmailResponseData,
    VerifyPasswordRequest,
    VerifyPasswordResetCodeRequest,
    VerifyPasswordResetCodeResponseData,
    VerifyPasswordResponseData,
    WithdrawAccountResponseData,
    WithdrawRequest,
)
from app.schemas.base import MessageResponseData
from app.services.base import BaseService
from app.services.oauth import GoogleOAuthService
from app.utils.email_service import EmailService
from app.utils.encryption import PasswordHasher
from app.utils.minio_upload import upload_image_with_thumbnail_to_minio
from app.utils.validators import validate_image_file

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService(BaseService):
    def __init__(
        self,
        db: Session,
        email_service: EmailService,
        google_oauth_service: GoogleOAuthService,
    ):
        super().__init__(db)
        assert email_service is not None, "EmailService must be provided"
        assert isinstance(
            email_service, EmailService
        ), "email_service must be an instance of EmailService"
        self._email_service = email_service
        self._google_oauth_service = google_oauth_service

    def login(self, request: LoginRequest):
        # 1. 사용자 조회 (Soft Delete 포함)
        stmt = select(User).where(User.email == request.email)
        result = self._db.execute(stmt)
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
        if not PasswordHasher.verify_password(request.password, user.password_hash):
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
        access_token = JWTHandler.create_access_token({"sub": str(user.id)})
        refresh_token = JWTHandler.create_refresh_token({"sub": str(user.id)})

        # 7. 응답 생성 (쿠키만 설정, 응답에는 토큰 제외)
        data = LoginResponseData(
            user_id=str(user.id),
            email=user.email,
            nickname=user.nickname,
            message="로그인이 완료되었습니다.",
        )

        logger.info(f"사용자 로그인: {user.email}")

        return data, access_token, refresh_token

    async def logout(self, user_id: UUID):
        error_details: list[str] = []

        with TransactionManager.transaction(self._db) as tx:
            # 사용자 정보 조회
            user_result = tx.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one()

            # 2. 구글 OAuth 세션 정리
            if (
                user.account_type == AccountType.SOCIAL.value
                and user.provider == OAuthProvider.GOOGLE.value
            ):
                oauth_token_result = tx.execute(
                    select(OAuthToken).where(
                        OAuthToken.user_id == user_id,
                        OAuthToken.provider == OAuthProvider.GOOGLE.value,
                    )
                )
                oauth_token = oauth_token_result.scalar_one()

                if oauth_token.access_token and not await self.__revoke_google_token(
                    oauth_token.access_token
                ):
                    error_details.append("Google token revocation failed")

                # 3. OAuth 토큰 무효화
                if user_id:
                    self.__invalidate_oauth_tokens(user_id, tx)

            # 4. 보안 로그 기록
            if user_id:
                self.__log_logout_attempt(user_id, ", ".join(error_details))

        return LogoutResponseData(
            logout_time=datetime.now(UTC).isoformat(),
            user_id=user_id,
            account_type=user.account_type if user else None,
            provider=(
                user.provider
                if user and user.account_type == AccountType.SOCIAL.value
                else None
            ),
            errors=error_details,
        )

    def refresh_token(self, refresh_token: str):
        # 1. Refresh Token 검증
        try:
            payload = JWTHandler.decode_token(refresh_token)
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
            ) from e

        # 2. 사용자 정보 조회
        stmt = select(User).where(User.id == user_id)
        result = self._db.execute(stmt)
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

        # 3. 새로운 토큰 발급
        access_token = JWTHandler.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        new_refresh_token = JWTHandler.create_refresh_token(data={"sub": str(user.id)})

        logger.info(f"토큰 갱신 성공: {user.email}")

        # 4. 쿠키에 새로운 토큰 설정
        data = RefreshTokenResponseData(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
        )

        return data, access_token, new_refresh_token

    def get_current_user_info(self, user_id: UUID):
        current_user = self._db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        ).scalar_one()

        return GetCurrentUserInfoResponseData(
            user_id=current_user.id,
            email=current_user.email,
            nickname=current_user.nickname,
            profile_image_url=current_user.profile_image_url,
            account_type=current_user.account_type,
            provider=current_user.provider,
            is_active=current_user.is_active,
            created_at=current_user.created_at.isoformat(),
        )

    def update_user_profile(self, user_id: UUID, request: UpdateUserProfileRequest):
        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == user_id)
            ).scalar_one()

            # 닉네임 업데이트
            current_user.nickname = request.nickname

            # 프로필 이미지 URL 업데이트 (제공된 경우)
            if request.profile_image_url is not None:
                current_user.profile_image_url = request.profile_image_url

            current_user.updated_at = datetime.now(UTC)

            logger.info(
                f"프로필 업데이트 성공: {current_user.email} -> {request.nickname}"
            )

        return UpdateUserProfileResponseData(
            user_id=current_user.id,
            nickname=current_user.nickname,
            profile_image_url=current_user.profile_image_url,
            updated_at=current_user.updated_at.isoformat(),
        )

    async def upload_profile_image(self, user_id: UUID, image: UploadFile):
        # 이미지 파일 검증
        validate_image_file(image.content_type, image.size)

        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == user_id)
            ).scalar_one()

            # MinIO에 이미지와 썸네일 업로드
            file_id, _original_url, thumbnail_url = (
                await upload_image_with_thumbnail_to_minio(image)
            )

            # 사용자 프로필에 이미지 URL 저장 (썸네일 사용)
            current_user.profile_image_url = thumbnail_url
            current_user.updated_at = datetime.now(UTC)

            logger.info(
                f"프로필 이미지 업로드 성공: {current_user.email} -> {thumbnail_url}"
            )

        return UploadProfileImageResponseData(
            image_url=thumbnail_url,
            file_id=file_id,
            user_id=current_user.id,
            updated_at=current_user.updated_at.isoformat(),
        )

    async def send_email_change_verification(
        self, current_user_id: UUID, new_email: str
    ):
        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == current_user_id)
            ).scalar_one()

            # 1. 새로운 이메일 중복 확인
            self.__check_duplicate_email(new_email, tx)

            # 2. 기존 이메일과 같은지 확인
            if new_email == current_user.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="현재 사용 중인 이메일과 동일합니다.",
                )

            # 3. 인증 토큰 생성
            verification_token = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=6)
            )

            # 4. 기존 인증 코드가 있다면 삭제
            existing_verification_result = tx.execute(
                select(EmailVerification).where(
                    EmailVerification.email == new_email,
                    EmailVerification.verification_type == "change",
                )
            )
            existing_verification = existing_verification_result.scalar_one_or_none()

            if existing_verification:
                tx.delete(existing_verification)

            # 5. 새로운 인증 토큰 저장
            new_verification = EmailVerification(
                email=new_email,
                verification_code=verification_token,
                verification_type="change",
                expires_at=datetime.now() + timedelta(minutes=30),
            )

            tx.add(new_verification)

            # 6. 인증 URL 생성
            verification_url = f"{settings.frontend_url}/profile?token={verification_token}&action=change-email"

            # 7. 실제 이메일 발송
            await self._email_service.send_email_change_verification(
                to_email=new_email,
                verification_url=verification_url,
                current_email=current_user.email,
            )

        return SendEmailChangeVerificationResponseData(
            message="인증 이메일이 발송되었습니다.",
            email_sent="true",
            target_email=new_email,
        )

    def verify_email_change_token(self, token: str, email: str | None = None):
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

        result = self._db.execute(stmt)
        verification = result.scalar_one_or_none()

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 인증 토큰입니다.",
            )

        return VerifyEmailChangeTokenResponseData(
            valid="true",
            email=verification.email,
            message="인증 토큰이 유효합니다.",
        )

    def verify_password_and_change_email(
        self,
        current_user_id: UUID,
        request: VerifyPasswordAndChangeEmailRequest,
    ):
        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == current_user_id)
            ).scalar_one()
            # 1. 이메일 회원가입 사용자인지 확인
            if current_user.account_type != AccountType.EMAIL.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="소셜 로그인 사용자는 비밀번호 확인이 필요하지 않습니다.",
                )

            # 2. 토큰 검증
            result = tx.execute(
                select(EmailVerification).where(
                    EmailVerification.email == request.new_email,
                    EmailVerification.verification_code == request.token,
                    EmailVerification.verification_type == "change",
                    EmailVerification.expires_at > datetime.now(),
                    EmailVerification.is_used.is_(False),
                )
            )
            verification = result.scalar_one_or_none()

            if not verification:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="유효하지 않은 인증 토큰입니다.",
                )

            # 3. 비밀번호 검증
            if not PasswordHasher.verify_password(
                request.password, current_user.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="비밀번호가 올바르지 않습니다.",
                )

            # 4. 새로운 이메일 중복 확인
            self.__check_duplicate_email(request.new_email, tx)

            # 5. 이메일 변경
            old_email = current_user.email
            current_user.email = request.new_email

            # 6. 토큰 사용 처리
            verification.is_used = True

            logger.info(f"이메일 변경 성공: {old_email} → {request.new_email}")

        return VerifyPasswordAndChangeEmailResponseData(
            message="이메일이 성공적으로 변경되었습니다.",
            email_changed="true",
            old_email=old_email,
            new_email=request.new_email,
            requires_logout="true",
        )

    def withdraw_account(
        self,
        current_user_id: UUID,
        request: WithdrawRequest,
    ):
        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == current_user_id)
            ).scalar_one()
            logger.info(f"탈퇴 요청 시작: {current_user.id}")

            # 1. 계정 타입별 비밀번호 확인
            if current_user.account_type == AccountType.EMAIL.value:
                if not request.password:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="이메일 계정은 비밀번호 확인이 필요합니다.",
                    )
                if not PasswordHasher.verify_password(
                    request.password, current_user.password_hash
                ):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="비밀번호가 올바르지 않습니다.",
                    )

            # 2. 탈퇴 처리
            withdrawal_date = datetime.now(UTC)

            # 3. User 테이블 Soft Delete
            tx.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(deleted_at=withdrawal_date)
            )

            # 4. Diary 테이블 Soft Delete
            tx.execute(
                update(DiaryEntry)
                .where(DiaryEntry.user_id == current_user.id)
                .values(deleted_at=withdrawal_date)
            )

            # 5. 관련 데이터 Hard Delete
            tx.execute(delete(FCMToken).where(FCMToken.user_id == current_user.id))
            tx.execute(
                delete(NotificationSettings).where(
                    NotificationSettings.user_id == current_user.id
                )
            )
            tx.execute(
                delete(NotificationHistory).where(
                    NotificationHistory.user_id == current_user.id
                )
            )
            tx.execute(
                delete(Notification).where(Notification.user_id == current_user.id)
            )
            tx.execute(delete(OAuthToken).where(OAuthToken.user_id == current_user.id))
            tx.execute(
                delete(EmailVerification).where(
                    EmailVerification.email == current_user.email
                )
            )

            logger.info(f"탈퇴 성공: {current_user.id}")

        return WithdrawAccountResponseData(
            message="계정 탈퇴가 완료되었습니다.",
            withdrawal_date=withdrawal_date.isoformat(),
            restore_until=(withdrawal_date + timedelta(days=30)).isoformat(),
            success=True,
        )

    async def send_password_reset_email(self, request: SendPasswordResetEmailRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 사용자 조회
            user_result = tx.execute(select(User).where(User.email == request.email))
            user = user_result.scalar_one_or_none()

            if not user:
                return SendPasswordResetEmailResponseData(
                    success=False,
                    message="해당 이메일로 가입된 계정이 없습니다.",
                    is_social_account=False,
                    email_sent=False,
                )

            # 소셜 계정 사용자인 경우
            if user.account_type == AccountType.SOCIAL.value:
                provider_name = user.provider or "소셜"
                return SendPasswordResetEmailResponseData(
                    success=False,
                    message=f"소셜 계정 사용자입니다. {provider_name} 계정으로 가입된 사용자입니다. 비밀번호 재설정은 해당 서비스에서 직접 진행해주세요.",
                    is_social_account=True,
                    email_sent=False,
                    redirect_to_error_page=True,
                )

            # 이메일 계정 사용자인 경우
            # 기존 토큰이 있다면 만료 처리
            token_result = tx.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.is_used.is_(False),
                )
            )
            existing_tokens = token_result.scalars().all()

            for token in existing_tokens:
                token.is_used = True
                token.used_at = datetime.now(UTC)

            # 새로운 토큰 생성
            token_value = str(uuid4())
            expires_at = datetime.now(UTC) + timedelta(hours=1)

            reset_token = PasswordResetToken(
                user_id=user.id,
                token=token_value,
                expires_at=expires_at,
                is_used=False,
            )

            tx.add(reset_token)

            # 비밀번호 재설정 이메일 발송
            reset_url = f"{settings.frontend_url}/reset-password?token={token_value}"

            _email_sent = await self._email_service.send_password_reset_email(
                to_email=user.email,
                nickname=user.nickname,
                reset_url=reset_url,
            )

            # CHECK: 확인 필요
            # if not email_sent:
            #     return BaseResponse(
            #         success=False,
            #         data=SendPasswordResetEmailResponseData(
            #             success=False,
            #             message="이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.",
            #             is_social_account=False,
            #             email_sent=False,
            #         ),
            #         message="이메일 발송에 실패했습니다.",
            #     )

        return SendPasswordResetEmailResponseData(
            success=True,
            message="비밀번호 재설정 이메일을 발송했습니다.",
            is_social_account=False,
            email_sent=True,
        )

    def verify_password_reset_code(self, request: VerifyPasswordResetCodeRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 사용자 조회
            user_result = tx.execute(select(User).where(User.email == request.email))
            user = user_result.scalar_one_or_none()

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
            token_result = tx.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.token == request.verification_code,
                    PasswordResetToken.is_used.is_(False),
                    PasswordResetToken.expires_at > datetime.now(UTC),
                )
            )
            token = token_result.scalar_one_or_none()

            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="유효하지 않은 인증코드입니다.",
                )

        return VerifyPasswordResetCodeResponseData(
            verified=True,
        )

    def reset_password(self, request: ResetPasswordRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 사용자 조회
            user_result = tx.execute(select(User).where(User.email == request.email))
            user = user_result.scalar_one_or_none()

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
            token_result = self._db.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.token == request.verification_code,
                    PasswordResetToken.is_used.is_(False),
                    PasswordResetToken.expires_at > datetime.now(UTC),
                )
            )
            token = token_result.scalar_one_or_none()

            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="유효하지 않은 인증코드입니다.",
                )

            # 비밀번호 해시화 및 업데이트
            user.password_hash = PasswordHasher.hash_password(request.new_password)

            # 토큰 사용 처리
            token.is_used = True
            token.used_at = datetime.now(UTC)

        return ResetPasswordResponseData(
            message="비밀번호가 성공적으로 변경되었습니다.",
        )

    def change_password(self, current_user_id: UUID, request: ChangePasswordRequest):
        with TransactionManager.transaction(self._db) as tx:
            current_user = tx.execute(
                select(User).where(User.id == current_user_id)
            ).scalar_one()

            # 소셜 계정 사용자인 경우
            if current_user.account_type == AccountType.SOCIAL.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="소셜 계정 사용자는 비밀번호 변경이 불가능합니다.",
                )

            # 현재 비밀번호 확인
            if not PasswordHasher.verify_password(
                request.current_password, current_user.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="현재 비밀번호가 올바르지 않습니다.",
                )

            # 새 비밀번호 해시화 및 업데이트
            current_user.password_hash = PasswordHasher.hash_password(
                request.new_password
            )

        return ChangePasswordResponseData(
            message="비밀번호가 성공적으로 변경되었습니다.",
        )

    def verify_password(self, current_user: User, request: VerifyPasswordRequest):
        # 이메일 회원가입 사용자인지 확인
        if current_user.account_type != AccountType.EMAIL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소셜 로그인 사용자는 비밀번호 확인이 불가능합니다.",
            )

        # 현재 비밀번호 확인
        if not PasswordHasher.verify_password(
            request.current_password, current_user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )

        return VerifyPasswordResponseData(
            message="비밀번호 확인 완료",
        )

    async def send_restore_email(self, request: SendRestoreEmailRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 탈퇴된 사용자 확인
            user_result = tx.execute(
                select(User).where(
                    User.email == request.email, User.deleted_at.is_not(None)
                )
            )
            user = user_result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="탈퇴된 계정을 찾을 수 없습니다.",
                )

            # 2. 30일 이내인지 확인
            current_time = (
                datetime.now(user.deleted_at.tzinfo)
                if user.deleted_at
                else datetime.now()
            )
            deleted_time = (
                user.deleted_at.replace(tzinfo=None)
                if user.deleted_at
                else user.deleted_at
            )
            current_time_naive = (
                current_time.replace(tzinfo=None)
                if current_time.tzinfo
                else current_time
            )

            if deleted_time and deleted_time < current_time_naive - timedelta(days=30):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                )

            # 3. 인증 코드 생성 (6자리 숫자)
            verification_code = str(random.randint(100000, 999999))

            # 4. 기존 인증 코드가 있다면 만료 처리
            email_verification_result = tx.execute(
                select(EmailVerification).where(
                    EmailVerification.email == request.email,
                    EmailVerification.verification_type == "restore",
                    EmailVerification.expires_at > datetime.now(),
                )
            )
            existing_verification = email_verification_result.scalar_one_or_none()

            if existing_verification:
                existing_verification.expires_at = datetime.now() - timedelta(seconds=1)
                existing_verification.is_used = True

            # 5. 새로운 인증 코드 저장
            new_verification = EmailVerification(
                email=request.email,
                verification_code=verification_code,
                verification_type="restore",
                expires_at=datetime.now() + timedelta(minutes=10),
            )

            tx.add(new_verification)

            # 6. 실제 이메일 발송
            email_sent = await self._email_service.send_verification_email(
                request.email, verification_code, "restore"
            )

            if not email_sent:
                # 이메일 발송 실패 시 인증 코드 삭제
                tx.delete(new_verification)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="복구 이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.",
                )

            logger.info(
                f"복구 이메일 발송 성공: {request.email} (인증코드: {verification_code})"
            )

        return SendRestoreEmailResponseData(
            message="복구 이메일이 발송되었습니다.",
        )

    def restore_account(self, request: RestoreAccountRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 탈퇴된 사용자 조회
            user_result = tx.execute(
                select(User).where(
                    User.email == request.email, User.deleted_at.is_not(None)
                )
            )
            user = user_result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="탈퇴된 계정을 찾을 수 없습니다.",
                )

            # 2. 30일 이내인지 확인
            current_time = (
                datetime.now(user.deleted_at.tzinfo)
                if user.deleted_at
                else datetime.now()
            )
            deleted_time = (
                user.deleted_at.replace(tzinfo=None)
                if user.deleted_at
                else user.deleted_at
            )
            current_time_naive = (
                current_time.replace(tzinfo=None)
                if current_time.tzinfo
                else current_time
            )

            if deleted_time and deleted_time < current_time_naive - timedelta(days=30):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                )

            # 3. 이메일 인증 코드 확인
            verification_result = tx.execute(
                select(EmailVerification).where(
                    EmailVerification.email == request.email,
                    EmailVerification.verification_code == request.verification_code,
                    EmailVerification.verification_type == "restore",
                    EmailVerification.expires_at > datetime.now(),
                    EmailVerification.is_used.is_(False),
                )
            )
            verification = verification_result.scalar_one_or_none()

            if not verification:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="유효하지 않은 인증 코드입니다.",
                )

            # 4. 인증 코드 사용 처리
            verification.is_used = True

            # 5. 계정 복구 처리
            restored_at = datetime.now()

            # User 테이블 복구
            tx.execute(update(User).where(User.id == user.id).values(deleted_at=None))

            # Diary 테이블 복구
            tx.execute(
                update(DiaryEntry)
                .where(DiaryEntry.user_id == user.id)
                .values(deleted_at=None)
            )

            # 6. 사용된 인증 코드 삭제
            tx.delete(verification)

            # 7. 응답 생성
            account_type_message = (
                "이메일 계정"
                if user.account_type == AccountType.EMAIL.value
                else "소셜 계정"
            )

        logger.info(f"계정 복구 성공: {user.email}")

        return RestoreAccountResponseData(
            message=f"{account_type_message}이 성공적으로 복구되었습니다.",
            restored_at=restored_at,
            user_id=str(user.id),
            email=user.email,
            nickname=user.nickname,
        )

    async def google_login_with_id_token(self, request: GoogleLoginRequest):
        with TransactionManager.transaction(self._db) as tx:
            user = await self._google_oauth_service.authenticate(request, tx)

            access_token = JWTHandler.create_access_token({"sub": str(user.id)})
            refresh_token = JWTHandler.create_refresh_token({"sub": str(user.id)})

            data = LoginResponseData(
                user_id=str(user.id),
                email=user.email,
                nickname=user.nickname,
                message="구글 로그인이 완료되었습니다.",
            )

            return data, access_token, refresh_token

    async def google_callback(self, code: str):
        with TransactionManager.transaction(self._db) as tx:
            user, _ = await self._google_oauth_service.process_oauth_callback(code, tx)

            # JWT 토큰 생성
            access_token = JWTHandler.create_access_token({"sub": str(user.id)})
            refresh_token = JWTHandler.create_refresh_token({"sub": str(user.id)})

            return (
                f"{settings.frontend_callback_url}?success=true",
                access_token,
                refresh_token,
            )

    # CHECK: OauthService 로 이동되어야할듯
    async def __revoke_google_token(self, access_token: str) -> bool:
        """구글 OAuth 토큰 무효화"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    data={"token": access_token},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Google token revocation failed: {e}")
            return False

    def __invalidate_oauth_tokens(self, user_id: UUID, tx: Session) -> None:
        """사용자의 OAuth 토큰들을 무효화"""
        # 사용자의 OAuth 토큰 조회
        stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
        result = tx.execute(stmt)
        oauth_tokens = result.scalars().all()

        for oauth_token in oauth_tokens:
            # 토큰 만료 시간을 현재 시간으로 설정하여 무효화
            oauth_token.expires_at = datetime.now(UTC)

        logger.info(f"Invalidated {len(oauth_tokens)} OAuth tokens for user {user_id}")

    def __log_logout_attempt(
        self,
        user_id: UUID,
        details: str = "",
    ) -> None:
        """로그아웃 시도 기록"""
        log_message = f"Logout attempt - User: {user_id}"
        if details:
            log_message += f", Details: {details}"

        logger.info(log_message)

    async def sign_up(self, request: SignupRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 이메일 중복 확인
            self.__check_duplicate_email(request.email, tx)

            # 2. 이메일 인증 확인
            email_verification = self.__check_verified_email(request.email, tx)

            # 3. 닉네임 중복 확인
            self.__check_duplicate_nickname(request.nickname, tx)

            # 4. 비밀번호 해싱
            hashed_password = PasswordHasher.hash_password(request.password)

            # 5. 사용자 생성
            new_user = User(
                email=request.email,
                password_hash=hashed_password,
                nickname=request.nickname,
                account_type=AccountType.EMAIL.value,
                provider=None,
                provider_id=None,
                is_active=True,
            )

            tx.add(new_user)
            tx.commit()
            tx.refresh(new_user)

            # 6. 이메일 인증 기록 삭제 (회원가입 완료 후)
            tx.delete(email_verification)
            tx.commit()

            # 7. 환영 이메일 발송
            await self._email_service.send_welcome_email(
                new_user.email, new_user.nickname
            )

            logger.info(f"새 사용자 가입: {new_user.email}")

            return SignUpResponseData(
                user_id=str(new_user.id),
                email=new_user.email,
                nickname=new_user.nickname,
                message="회원가입이 완료되었습니다.",
            )

    def __check_duplicate_email(self, email: str, tx: Session):
        stmt = select(User).where(User.email == email)
        result = tx.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise DuplicateEmailException(email)

    def __check_verified_email(self, email: str, tx: Session):
        stmt = select(EmailVerification).where(
            EmailVerification.email == email,
            EmailVerification.verification_type == "signup",
            EmailVerification.is_used.is_(True),
        )
        result = tx.execute(stmt)
        email_verification = result.scalar_one_or_none()

        if not email_verification:
            raise NeedVerifyEmailException(email)

        return email_verification

    def __check_duplicate_nickname(self, nickname: str, tx: Session):
        stmt = select(User).where(User.nickname == nickname)
        result = tx.execute(stmt)
        existing_nickname = result.scalar_one_or_none()

        if existing_nickname:
            raise DuplicateNicknameException(nickname)

    def check_email_availability(self, email: str):
        stmt = select(User).where(User.email == email)
        result = self._db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        return {
            "available": existing_user is None,
            "message": (
                "사용 가능한 이메일입니다."
                if existing_user is None
                else "이미 사용 중인 이메일입니다."
            ),
        }

    def check_nickname_availability(self, nickname: str):
        stmt = select(User).where(User.nickname == nickname)
        result = self._db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        return {
            "available": existing_user is None,
            "message": (
                "사용 가능한 닉네임입니다."
                if existing_user is None
                else "이미 사용 중인 닉네임입니다."
            ),
        }

    async def send_verification_email(self, request: EmailVerificationRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 이메일 중복 확인
            self.__check_duplicate_email(request.email, tx)

            # 2. 인증 코드 생성 (6자리 숫자)
            verification_code = str(randint(100000, 999999))

            # 3. 기존 인증 코드가 있다면 삭제
            stmt = select(EmailVerification).where(
                EmailVerification.email == request.email
            )
            result = tx.execute(stmt)
            existing_verification = result.scalar_one_or_none()

            if existing_verification:
                tx.delete(existing_verification)

            # 4. 새로운 인증 코드 저장
            new_verification = EmailVerification(
                email=request.email,
                verification_code=verification_code,
                verification_type="signup",
                expires_at=datetime.now() + timedelta(minutes=10),
            )

            tx.add(new_verification)

            # 5. 실제 이메일 발송
            email_sent = await self._email_service.send_verification_email(
                request.email, verification_code
            )

            if not email_sent:
                # 이메일 발송 실패 시 인증 코드 삭제
                tx.delete(new_verification)
                raise SendVerificationEmailException(request.email)

            logger.info(f"인증 코드 발송: {request.email}")

        return MessageResponseData(message="인증 코드가 발송되었습니다.")

    def verify_email(self, request: EmailVerificationConfirmRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 인증 코드 조회
            stmt = select(EmailVerification).where(
                EmailVerification.email == request.email,
                EmailVerification.verification_code == request.verification_code,
                EmailVerification.verification_type == "signup",
                EmailVerification.expires_at > datetime.now(),
                EmailVerification.is_used.is_(False),
            )
            result = tx.execute(stmt)
            verification = result.scalar_one_or_none()

            if not verification:
                raise MismatchedVerificationCodeException(request.email)

            # 2. 인증 완료 처리
            verification.is_used = True

            logger.info(f"이메일 인증 완료: {request.email}")

        return MessageResponseData(message="이메일 인증이 완료되었습니다.")
