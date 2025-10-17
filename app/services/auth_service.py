import logging
from datetime import datetime, timedelta
from random import randint

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import AccountType
from app.core.transaction_manager import TransactionManager
from app.exceptions.auth import (
    DuplicateEmailException,
    DuplicateNicknameException,
    MismatchedVerificationCodeException,
    NeedVerifyEmailException,
    SendVerificationEmailException,
)
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationConfirmRequest,
    EmailVerificationRequest,
    SignupRequest,
    SignUpResponseData,
)
from app.schemas.base import MessageResponseData
from app.services.base import BaseService
from app.utils.email_service import EmailService
from app.utils.encryption import password_hasher

logger = logging.getLogger(__name__)


class AuthService(BaseService):
    def __init__(self, db: Session, email_service: EmailService):
        super().__init__(db)
        assert email_service is not None, "EmailService must be provided"
        assert isinstance(
            email_service, EmailService
        ), "email_service must be an instance of EmailService"
        self._email_service = email_service

    async def sign_up(self, request: SignupRequest):
        with TransactionManager.transaction(self._db) as tx:
            # 1. 이메일 중복 확인
            self.__check_duplicate_email(request.email, tx)

            # 2. 이메일 인증 확인
            email_verification = self.__check_verified_email(request.email, tx)

            # 3. 닉네임 중복 확인
            self.__check_duplicate_nickname(request.nickname, tx)

            # 4. 비밀번호 해싱
            hashed_password = password_hasher.hash_password(request.password)

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
