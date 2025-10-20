from app.exceptions.base import BusinessException


class AppVersionServiceException(BusinessException):
    """앱 버전 서비스 예외 클래스"""

    pass


class LatestVersionNotFoundException(AppVersionServiceException):
    """최신 버전 없음 예외"""

    def __init__(self, platform: str):
        super().__init__(
            status_code=404,
            detail=f"{platform.capitalize()} 플랫폼의 최신 버전을 찾을 수 없습니다.",
            error_code="LATEST_VERSION_NOT_FOUND",
        )


class AppVersionAlreadyExistsException(AppVersionServiceException):
    """앱 버전 이미 존재 예외"""

    def __init__(self, platform: str, version_name: str):
        super().__init__(
            status_code=409,
            detail=f"{platform} 플랫폼에 버전 '{version_name}'이(가) 이미 존재합니다.",
            error_code="APP_VERSION_ALREADY_EXISTS",
        )
