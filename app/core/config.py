"""애플리케이션 설정"""

import os
from enum import StrEnum
from functools import lru_cache
from typing import Any, cast

from pydantic import field_validator
from pydantic_settings import BaseSettings


class AppEnvironment(StrEnum):
    """애플리케이션 환경을 문자열 Enum으로 정의"""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class CookieSameSite(StrEnum):
    """쿠키 SameSite 옵션을 문자열 Enum으로 정의"""

    LAX = "lax"
    STRICT = "strict"
    NONE = "none"


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 기본 설정
    app_name: str = "새김 - 감성 AI 다이어리"
    debug: bool = False
    version: str = "1.0.0"
    environment: AppEnvironment = AppEnvironment.DEVELOPMENT

    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000

    # 데이터베이스 설정
    database_url: str = os.getenv("DATABASE_URL", "")
    database_echo: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    database_pool_timeout: int = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
    database_pool_recycle: int = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
    database_ssl_mode: str = os.getenv("DATABASE_SSL_MODE", "prefer")

    # 보안 설정 (환경변수에서 필수로 가져오기)
    secret_key: str = os.getenv("SECRET_KEY", "")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")

    # JWT 설정
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    jwt_refresh_token_expire_days: int = int(
        os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
    )

    # MinIO 설정
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    minio_bucket_name: str = os.getenv("MINIO_BUCKET_NAME", "saegim")

    # CORS 설정 (환경변수에서 쉼표로 구분된 문자열을 리스트로 변환)
    allowed_hosts: str | list[str] = os.getenv(
        "ALLOWED_HOSTS",
        "http://localhost:3000,http://localhost:3001,http://localhost:8080",
    )

    # 이미지 프록시 설정
    image_proxy_allowed_domains: str | list[str] = os.getenv(
        "IMAGE_PROXY_ALLOWED_DOMAINS",
        "",
    )

    # FCM 설정
    fcm_project_id: str = os.getenv("FCM_PROJECT_ID", "")
    fcm_service_account_json: str = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")

    # Google OAuth 설정
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )
    google_auth_uri: str = os.getenv(
        "GOOGLE_AUTH_URI", "https://accounts.google.com/oauth2/auth"
    )
    google_token_uri: str = os.getenv(
        "GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"
    )
    google_userinfo_uri: str = os.getenv(
        "GOOGLE_USERINFO_URI", "https://www.googleapis.com/oauth2/v2/userinfo"
    )
    google_android_client_ids: str | list[str] = os.getenv(
        "GOOGLE_ANDROID_CLIENT_IDS", ""
    )

    # 프론트엔드 URL 설정
    frontend_url: str = os.getenv("FRONTEND_URL", "")
    frontend_callback_url: str = os.getenv("FRONTEND_CALLBACK_URL", "")

    # 이메일 설정
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    from_email: str = os.getenv("FROM_EMAIL", "noreply@saegim.com")

    # SendGrid 설정
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    sendgrid_from_email: str = os.getenv("SENDGRID_FROM_EMAIL", "")

    # OpenAI 설정
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_default_model: str = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4")

    # AI 서비스 설정
    ai_max_regeneration_count: int = int(os.getenv("AI_MAX_REGENERATION_COUNT", "5"))
    ai_max_keywords: int = int(os.getenv("AI_MAX_KEYWORDS", "5"))
    ai_notification_threshold_seconds: int = int(
        os.getenv("AI_NOTIFICATION_THRESHOLD_SECONDS", "3")
    )

    # FCM 재시도 설정
    fcm_max_retries: int = int(os.getenv("FCM_MAX_RETRIES", "3"))
    fcm_retry_delay: float = float(os.getenv("FCM_RETRY_DELAY", "0.1"))

    # 쿠키 설정 (Enum으로 처리, env에서 문자열로 읽어들임)
    cookie_domain: str = os.getenv("COOKIE_DOMAIN", "localhost")
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    cookie_samesite: CookieSameSite = CookieSameSite(
        os.getenv("COOKIE_SAMESITE", "lax")
    )
    cookie_httponly: bool = os.getenv("COOKIE_HTTPONLY", "true").lower() == "true"

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: Any) -> list[str]:
        """ALLOWED_HOSTS 환경변수를 리스트로 파싱"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return cast(list[str], v)
        return []

    @field_validator("image_proxy_allowed_domains", mode="before")
    @classmethod
    def parse_image_proxy_allowed_domains(cls, v: Any) -> list[str]:
        """IMAGE_PROXY_ALLOWED_DOMAINS 환경변수를 리스트로 파싱"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return cast(list[str], v)
        return []

    @field_validator("google_android_client_ids", mode="before")
    @classmethod
    def parse_google_android_client_ids(cls, v: Any) -> list[str]:
        """안드로이드용 구글 클라이언트 ID 목록 파싱"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return cast(list[str], v)
        return []

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def parse_cookie_samesite(cls, v: Any) -> CookieSameSite:
        """COOKIE_SAMESITE 환경변수를 CookieSameSite Enum으로 파싱"""
        if isinstance(v, CookieSameSite):
            return v
        if isinstance(v, str):
            val = v.strip().lower()
            try:
                return CookieSameSite(val)
            except ValueError:
                # 허용되지 않는 값이면 안전하게 기본값으로 폴백
                return CookieSameSite.LAX
        # 타입이 맞지 않으면 기본값 반환
        return CookieSameSite.LAX

    @property
    def is_development(self) -> bool:
        """개발 환경인지 확인"""
        return self.environment == AppEnvironment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """운영 환경인지 확인"""
        return self.environment == AppEnvironment.PRODUCTION

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins 반환"""
        # allowed_hosts가 field_validator로 처리되어 항상 list 타입임
        return self.allowed_hosts if isinstance(self.allowed_hosts, list) else []

    @property
    def image_proxy_domains(self) -> list[str]:
        """이미지 프록시 허용 도메인 반환"""
        # image_proxy_allowed_domains가 field_validator로 처리되어 항상 list 타입임
        return (
            self.image_proxy_allowed_domains
            if isinstance(self.image_proxy_allowed_domains, list)
            else []
        )

    @property
    def google_allowed_audiences(self) -> list[str]:
        """구글 ID 토큰 검증 시 허용할 클라이언트 ID 목록"""
        audiences: set[str] = set()
        if self.google_client_id:
            audiences.add(self.google_client_id)
        if isinstance(self.google_android_client_ids, list):
            for client_id in self.google_android_client_ids:
                if client_id:
                    audiences.add(client_id)
        return list(audiences)

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

    def model_post_init(self, __context: dict[str, Any]) -> None:
        """설정 초기화 후 필수 환경변수 검증"""
        if not self.secret_key:
            raise ValueError(
                "SECRET_KEY 환경변수가 설정되지 않았습니다. "
                "보안을 위해 반드시 설정해야 합니다."
            )
        if not self.encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY 환경변수가 설정되지 않았습니다. "
                "데이터 암호화를 위해 반드시 설정해야 합니다."
            )
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY는 보안을 위해 최소 32자 이상이어야 합니다.")
        if len(self.encryption_key) < 32:
            raise ValueError(
                "ENCRYPTION_KEY는 보안을 위해 최소 32자 이상이어야 합니다."
            )

    @property
    def cookie_samesite_value(self) -> str:
        """Enum을 사용하는 경우 문자열 값으로 반환(기존 코드 호환용)"""
        return self.cookie_samesite.value


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 인스턴스 반환"""
    return Settings()


# 전역 settings 객체 생성
settings = get_settings()
