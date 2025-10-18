"""
표준화된 HTTP 에러 처리 팩토리
HTTPException 중복 제거 및 일관된 에러 응답 제공
"""

from typing import Any

from fastapi import HTTPException, status


class ErrorFactory:
    """표준화된 HTTP 에러 생성 팩토리"""

    # 인증 관련 에러
    @staticmethod
    def unauthorized(
        message: str = "인증이 필요합니다", details: dict[str, Any] | None = None
    ) -> HTTPException:
        """401 Unauthorized 에러 생성"""
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                {"error": "UNAUTHORIZED", "message": message, "details": details}
                if details
                else message
            ),
        )

    @staticmethod
    def forbidden(
        message: str = "접근 권한이 없습니다", details: dict[str, Any] | None = None
    ) -> HTTPException:
        """403 Forbidden 에러 생성"""
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                {"error": "FORBIDDEN", "message": message, "details": details}
                if details
                else message
            ),
        )

    @staticmethod
    def not_found(
        resource: str = "리소스", resource_id: str | None = None
    ) -> HTTPException:
        """404 Not Found 에러 생성"""
        message = f"{resource}를 찾을 수 없습니다"
        if resource_id:
            message += f" (ID: {resource_id})"

        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NOT_FOUND",
                "message": message,
                "resource": resource,
                "resource_id": resource_id,
            },
        )

    @staticmethod
    def bad_request(
        message: str = "잘못된 요청입니다", details: dict[str, Any] | None = None
    ) -> HTTPException:
        """400 Bad Request 에러 생성"""
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                {"error": "BAD_REQUEST", "message": message, "details": details}
                if details
                else message
            ),
        )

    @staticmethod
    def internal_error(
        message: str = "서버 내부 오류가 발생했습니다", error_code: str | None = None
    ) -> HTTPException:
        """500 Internal Server Error 생성"""
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "INTERNAL_SERVER_ERROR",
                "message": message,
                "error_code": error_code,
            },
        )

    @staticmethod
    def validation_error(
        field: str, message: str, value: Any | None = None
    ) -> HTTPException:
        """422 Validation Error 생성"""
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"{field}: {message}",
                "field": field,
                "invalid_value": value,
            },
        )


class AuthenticationErrors:
    """인증 관련 표준 에러들"""

    @staticmethod
    def token_required() -> HTTPException:
        """토큰 필요 에러"""
        return ErrorFactory.unauthorized("인증 토큰이 필요합니다")

    @staticmethod
    def token_invalid() -> HTTPException:
        """토큰 무효 에러"""
        return ErrorFactory.unauthorized("유효하지 않은 토큰입니다")

    @staticmethod
    def token_expired() -> HTTPException:
        """토큰 만료 에러"""
        return ErrorFactory.unauthorized("토큰이 만료되었습니다")

    @staticmethod
    def user_not_found(user_id: str | None = None) -> HTTPException:
        """사용자 없음 에러"""
        return ErrorFactory.not_found("사용자", user_id)

    @staticmethod
    def account_inactive() -> HTTPException:
        """계정 비활성화 에러"""
        return ErrorFactory.forbidden("비활성화된 계정입니다")

    @staticmethod
    def invalid_user_id_format() -> HTTPException:
        """사용자 ID 형식 오류"""
        return ErrorFactory.validation_error(
            "user_id", "올바르지 않은 사용자 ID 형식입니다"
        )


class OAuthErrors:
    """OAuth 관련 표준 에러들"""

    @staticmethod
    def token_request_failed(details: str | None = None) -> HTTPException:
        """토큰 요청 실패"""
        return ErrorFactory.bad_request(
            "액세스 토큰 요청에 실패했습니다", {"details": details} if details else None
        )

    @staticmethod
    def userinfo_request_failed() -> HTTPException:
        """사용자 정보 요청 실패"""
        return ErrorFactory.bad_request("사용자 정보 요청에 실패했습니다")

    @staticmethod
    def account_deleted(deleted_at: str, days_remaining: int) -> HTTPException:
        """삭제된 계정 에러"""
        return ErrorFactory.forbidden(
            "탈퇴된 계정입니다",
            {
                "error": "ACCOUNT_DELETED",
                "message": "탈퇴된 계정입니다. 30일 이내에 복구할 수 있습니다.",
                "deleted_at": deleted_at,
                "restore_available": True,
                "days_remaining": days_remaining,
            },
        )

    @staticmethod
    def account_permanently_deleted(deleted_at: str) -> HTTPException:
        """영구 삭제된 계정 에러"""
        return ErrorFactory.forbidden(
            "복구 불가능한 계정입니다",
            {
                "error": "ACCOUNT_PERMANENTLY_DELETED",
                "message": "탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                "deleted_at": deleted_at,
                "restore_available": False,
            },
        )
