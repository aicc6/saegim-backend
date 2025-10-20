"""
다이어리 관련 예외 클래스들
"""

from uuid import UUID

from .base import BusinessException


class DiaryServiceException(BusinessException):
    """다이어리 서비스 관련 예외 기본 클래스"""

    pass


class DiaryNotFoundException(DiaryServiceException):
    """다이어리를 찾을 수 없는 예외"""

    def __init__(self, diary_id: UUID):
        self.diary_id = diary_id

        detail = f"다이어리를 찾을 수 없습니다: {diary_id}"

        super().__init__(
            status_code=404,
            detail=detail,
            error_code="DIARY_NOT_FOUND",
        )


class DiaryAlreadyDeletedException(DiaryServiceException):
    """이미 삭제된 다이어리 예외"""

    def __init__(self, diary_id: UUID):
        self.diary_id = diary_id

        detail = f"이미 삭제된 다이어리입니다: {diary_id}"

        super().__init__(
            status_code=410,
            detail=detail,
            error_code="DIARY_ALREADY_DELETED",
        )


class DiaryAccessDeniedException(DiaryServiceException):
    """다이어리 접근 권한 없음 예외"""

    def __init__(self, diary_id: UUID, user_id: UUID, action: str = "access"):
        self.diary_id = diary_id
        self.user_id = user_id
        self.action = action

        detail = f"다이어리에 대한 {action} 권한이 없습니다."

        super().__init__(
            status_code=403,
            detail=detail,
            error_code="DIARY_ACCESS_DENIED",
        )


class DiaryImageAlreadyDeletedException(DiaryServiceException):
    """이미 삭제된 다이어리 이미지 예외"""

    def __init__(self, diary_id: UUID, image_id: UUID):
        self.diary_id = diary_id
        self.image_id = image_id

        detail = f"이미 삭제된 다이어리 이미지입니다: {diary_id}, {image_id}"

        super().__init__(
            status_code=410,
            detail=detail,
            error_code="DIARY_IMAGE_ALREADY_DELETED",
        )


class DiaryValidationException(DiaryServiceException):
    """다이어리 데이터 유효성 검사 예외"""

    def __init__(
        self,
        detail: str = "다이어리 데이터가 유효하지 않습니다.",
        field: str | None = None,
    ):
        self.field = field

        super().__init__(
            status_code=400,
            detail=detail,
            error_code="DIARY_VALIDATION_ERROR",
        )


class DiaryImageException(DiaryServiceException):
    """다이어리 이미지 관련 예외"""

    def __init__(
        self,
        detail: str = "이미지 처리 중 오류가 발생했습니다.",
        image_path: str | None = None,
    ):
        self.image_path = image_path

        super().__init__(
            status_code=500,
            detail=detail,
            error_code="DIARY_IMAGE_ERROR",
        )


class DiaryStorageLimitException(DiaryServiceException):
    """다이어리 저장 용량 제한 예외"""

    def __init__(self, used_size: int, limit_size: int, user_id: str | None = None):
        self.used_size = used_size
        self.limit_size = limit_size
        self.user_id = user_id

        detail = f"저장 용량을 초과했습니다. " f"사용량: {used_size}MB/{limit_size}MB"

        super().__init__(
            status_code=413,
            detail=detail,
            error_code="DIARY_STORAGE_LIMIT_EXCEEDED",
        )
