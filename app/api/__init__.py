"""
API 라우터
"""

from fastapi import APIRouter

from app.api.admin.cleanup import router as cleanup_router
from app.api.ai import router as ai_router
from app.api.app_version import router as app_version_router
from app.api.auth.authentication import (
    authenticated_router as auth_authenticated_router,
)
from app.api.auth.authentication import router as auth_router
from app.api.auth.oauth import router as oauth_router
from app.api.auth.registration import router as registration_router
from app.api.category import router as category_router
from app.api.diary import router as diary_router
from app.api.legacy import router as legacy_router
from app.api.notification import router as notification_router
from app.api.public import router as public_router
from app.api.support import router as support_router

router = APIRouter()

router.include_router(public_router, prefix="/api/public")
router.include_router(ai_router, prefix="/api/ai")
router.include_router(diary_router, prefix="/api/diary")
router.include_router(category_router, prefix="/api/categories")
router.include_router(notification_router, prefix="/api/notifications")
router.include_router(app_version_router, prefix="/api/app-version")  # 앱 버전 관리 API
router.include_router(legacy_router)  # 레거시 리다이렉트
router.include_router(support_router, prefix="/api/support")  # 고객센터 API

# Auth 라우터들을 /api/auth prefix로 통일
router.include_router(auth_router, prefix="/api/auth")
router.include_router(auth_authenticated_router, prefix="/api/auth")
router.include_router(oauth_router, prefix="/api/auth")
router.include_router(registration_router, prefix="/api/auth")
router.include_router(cleanup_router, prefix="/api/admin")
