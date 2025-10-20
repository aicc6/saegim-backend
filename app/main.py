"""
새김 백엔드 FastAPI 애플리케이션
"""

import logging
import os
from datetime import datetime

import psutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse

from app.api import router as api_router
from app.constants import HTTPHeaders
from app.core.config import get_settings
from app.core.env_config import load_env_file
from app.core.lifespan import lifespan
from app.exceptions.auth import DeletedAccountException
from app.schemas.base import HealthCheckResponse, HealthCheckResponseData

# 환경 변수 먼저 로드
load_env_file()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


# FastAPI 애플리케이션 인스턴스 생성
app = FastAPI(
    title=settings.app_name,
    description="감성 AI 다이어리 백엔드",
    version=settings.version,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)


def custom_openapi():
    """
    Swagger UI에 JWT Bearer Token 인증 버튼을 추가하기 위한 OpenAPI 스키마 커스터마이징
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # JWT Bearer Token Security Scheme 추가
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Authorization header using the Bearer scheme. Example: 'Authorization: Bearer {token}'",
        }
    }

    # 모든 보호된 엔드포인트에 기본 보안 적용
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            # 인증이 필요없는 엔드포인트 제외 (로그인, 회원가입, health 등)
            if (
                path.startswith("/api/auth/")
                or path in ["/", "/status", "/docs", "/redoc", "/openapi.json"]
                or path.startswith("/health")
            ):
                continue

            # 기타 모든 엔드포인트에 Bearer 토큰 보안 적용
            if "security" not in openapi_schema["paths"][path][method]:
                openapi_schema["paths"][path][method]["security"] = [{"bearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


# 커스텀 OpenAPI 스키마 적용
app.openapi = custom_openapi

# 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"] if settings.is_development else settings.cors_origins
    ),  # 개발환경에서는 모든 origin 허용
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        HTTPHeaders.AUTHORIZATION,
        HTTPHeaders.CONTENT_TYPE,
        HTTPHeaders.X_REQUESTED_WITH,
        HTTPHeaders.ACCEPT,
        HTTPHeaders.ORIGIN,
        HTTPHeaders.ACCESS_CONTROL_REQUEST_METHOD,
        HTTPHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
    ],  # 보안 강화: 구체적 헤더만 허용
)

# 프로덕션 환경에서만 적용되는 미들웨어
if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(HTTPSRedirectMiddleware)

# Gzip 압축
app.add_middleware(GZipMiddleware, minimum_size=1000)


# 전역 예외 핸들러
@app.exception_handler(DeletedAccountException)
async def deleted_account_exception_handler(
    _request: Request, exception: DeletedAccountException
):
    logger.info(f"Deleted account exception handler caught: {exception}")
    logger.info(exception.url)

    return RedirectResponse(url=exception.url)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "내부 서버 오류가 발생했습니다.",
            "timestamp": datetime.now().isoformat(),
        },
    )


def _get_uptime() -> int:
    """애플리케이션 업타임 계산 (초 단위)"""
    try:
        # 프로세스 시작 시간 기반 업타임 계산
        process = psutil.Process(os.getpid())
        create_time = datetime.fromtimestamp(process.create_time())
        uptime = datetime.now() - create_time
        return int(uptime.total_seconds())
    except Exception:
        return 0


# 통합 헬스체크 라우트
@app.get(
    "/",
    tags=["Health"],
    response_model=HealthCheckResponse,
)
async def health_check():
    """통합 헬스체크 엔드포인트 - 애플리케이션 상태 확인"""
    health_data = HealthCheckResponseData(
        status="healthy",
        app_name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        uptime=_get_uptime(),
    )

    return HealthCheckResponse(
        data=health_data,
        message="새김 백엔드가 정상적으로 실행 중입니다.",
    )


# API 라우터 등록
app.include_router(api_router)  # 일반 API 라우터 (prefix 포함)
