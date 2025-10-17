import logging

from .base import BusinessException

logger = logging.getLogger(__name__)


class AuthServiceException(BusinessException):
    """Auth 서비스 관련 예외 기본 클래스"""

    pass


class DuplicateEmailException(AuthServiceException):
    def __init__(
        self,
        email: str,
        detail: str = "이미 가입된 이메일입니다.",
    ):
        self.email = email

        logger.debug(f"Duplicate email attempted: {email}")

        super().__init__(
            status_code=400,
            detail=detail,
            error_code="DUPLICATE_EMAIL",
        )


class NeedVerifyEmailException(AuthServiceException):
    def __init__(
        self,
        email: str,
        detail: str = "이메일 인증이 필요합니다.",
    ):
        self.email = email

        logger.debug(f"Need email verification: {email}")

        super().__init__(
            status_code=400,
            detail=detail,
            error_code="NEED_VERIFY_EMAIL",
        )


class DuplicateNicknameException(AuthServiceException):
    def __init__(
        self,
        nickname: str,
        detail: str = "이미 사용 중인 닉네임입니다.",
    ):
        self.nickname = nickname

        logger.debug(f"Duplicate nickname attempted: {nickname}")

        super().__init__(
            status_code=400,
            detail=detail,
            error_code="DUPLICATE_NICKNAME",
        )


class SendVerificationEmailException(AuthServiceException):
    def __init__(
        self,
        email: str,
        detail: str = "이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.",
    ):
        self.email = email

        logger.debug(f"Failed to send verification email to: {email}")

        super().__init__(
            status_code=500,
            detail=detail,
            error_code="SEND_VERIFICATION_EMAIL_FAILED",
        )


class MismatchedVerificationCodeException(AuthServiceException):
    def __init__(
        self,
        email: str,
        detail: str = "유효하지 않은 인증 코드입니다.",
    ):
        self.email = email

        logger.debug(f"Mismatched verification code for email: {email}")

        super().__init__(
            status_code=400,
            detail=detail,
            error_code="MISMATCHED_VERIFICATION_CODE",
        )
