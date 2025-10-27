"""카테고리 관련 예외"""

from app.exceptions.base import BusinessException


class CategoryServiceException(BusinessException):
    """카테고리 서비스 예외 기본 클래스"""

    pass


class CategoryNotFoundException(CategoryServiceException):
    """카테고리를 찾을 수 없는 경우"""

    def __init__(self, category_id: str):
        super().__init__(
            status_code=404,
            detail=f"카테고리를 찾을 수 없습니다: {category_id}",
            error_code="CATEGORY_NOT_FOUND",
        )


class CategoryConflictException(CategoryServiceException):
    """카테고리 생성/수정 충돌"""

    def __init__(self, field: str, detail: str):
        super().__init__(
            status_code=409,
            detail=detail,
            error_code="CATEGORY_CONFLICT",
        )
        self.field = field


class CategoryValidationException(CategoryServiceException):
    """카테고리 유효성 검사 실패"""

    def __init__(self, detail: str, field: str | None = None):
        super().__init__(
            status_code=400,
            detail=detail,
            error_code="CATEGORY_VALIDATION_ERROR",
        )
        self.field = field
