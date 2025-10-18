"""
보안 및 인증 관련 유틸리티
JWT 토큰 생성/검증, 의존성 주입
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer

from app.constants import AuthConstants, ResponseMessages
from app.core.config import get_settings
from app.utils import data_encryptor, password_hasher

settings = get_settings()
security = HTTPBearer()


class JWTHandler:
    """JWT 토큰 처리 클래스"""

    @staticmethod
    def create_access_token(
        data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        """
        JWT 액세스 토큰 생성

        Args:
            data: 토큰에 포함할 데이터
            expires_delta: 만료 시간 (기본값: 1시간)

        Returns:
            JWT 토큰
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(
                minutes=settings.jwt_access_token_expire_minutes
            )

        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.now(UTC),
                "jti": str(uuid.uuid4()),  # JWT ID
                "type": AuthConstants.TOKEN_TYPE_ACCESS,
            }
        )

        return jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def create_refresh_token(
        data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        """
        JWT 리프레시 토큰 생성

        Args:
            data: 토큰에 포함할 데이터
            expires_delta: 만료 시간 (기본값: 7일)

        Returns:
            JWT 리프레시 토큰
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )

        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.now(UTC),
                "jti": str(uuid.uuid4()),
                "type": AuthConstants.TOKEN_TYPE_REFRESH,
            }
        )

        return jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def decode_token(token: str) -> dict[str, Any]:
        """
        JWT 토큰 디코딩 및 검증

        Args:
            token: JWT 토큰

        Returns:
            토큰 페이로드

        Raises:
            HTTPException: 토큰 검증 실패 시
        """
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload

        except jwt.ExpiredSignatureError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseMessages.TOKEN_EXPIRED,
                headers={
                    AuthConstants.HEADER_WWW_AUTHENTICATE: AuthConstants.TOKEN_TYPE_BEARER
                },
            ) from e
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseMessages.INVALID_TOKEN,
                headers={
                    AuthConstants.HEADER_WWW_AUTHENTICATE: AuthConstants.TOKEN_TYPE_BEARER
                },
            ) from e

    @staticmethod
    def verify_token_type(payload: dict[str, Any], expected_type: str) -> bool:
        """
        토큰 타입 검증

        Args:
            payload: 토큰 페이로드
            expected_type: 예상 토큰 타입 ('access' 또는 'refresh')

        Returns:
            검증 결과
        """
        return payload.get("type") == expected_type


class SecurityService:
    """보안 서비스 통합 클래스"""

    def __init__(self):
        self.jwt_handler = JWTHandler()
        self.password_hasher = password_hasher
        self.data_encryptor = data_encryptor

    def create_user_tokens(self, user_id: int) -> dict[str, str]:
        """
        사용자용 액세스/리프레시 토큰 생성

        Args:
            user_id: 사용자 ID

        Returns:
            액세스 토큰과 리프레시 토큰
        """
        token_data = {"sub": str(user_id)}

        access_token = self.jwt_handler.create_access_token(token_data)
        refresh_token = self.jwt_handler.create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": AuthConstants.TOKEN_TYPE_BEARER,
        }

    def refresh_access_token(self, refresh_token: str) -> str:
        """
        리프레시 토큰으로 새 액세스 토큰 생성

        Args:
            refresh_token: 리프레시 토큰

        Returns:
            새 액세스 토큰

        Raises:
            HTTPException: 토큰 검증 실패 시
        """
        payload = self.jwt_handler.decode_token(refresh_token)

        if not self.jwt_handler.verify_token_type(
            payload, AuthConstants.TOKEN_TYPE_REFRESH
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseMessages.TOKEN_NOT_REFRESH_TYPE,
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 토큰입니다.",
            )

        return self.jwt_handler.create_access_token({"sub": user_id})

    def encrypt_sensitive_fields(
        self, data: dict[str, Any], sensitive_fields: list[str]
    ) -> dict[str, Any]:
        """
        민감한 필드 암호화

        Args:
            data: 원본 데이터
            sensitive_fields: 암호화할 필드 목록

        Returns:
            암호화된 데이터
        """
        return self.data_encryptor.encrypt_dict(data, sensitive_fields)

    def decrypt_sensitive_fields(
        self, data: dict[str, Any], sensitive_fields: list[str]
    ) -> dict[str, Any]:
        """
        민감한 필드 복호화

        Args:
            data: 암호화된 데이터
            sensitive_fields: 복호화할 필드 목록

        Returns:
            복호화된 데이터
        """
        return self.data_encryptor.decrypt_dict(data, sensitive_fields)


# 전역 보안 서비스 인스턴스
security_service = SecurityService()


def get_current_user_id_from_cookie(
    request: Request,
) -> UUID:
    """
    쿠키에서 현재 사용자 ID 의존성

    Args:
        request: FastAPI Request 객체

    Returns:
        사용자 ID

    Raises:
        HTTPException: 인증 실패 시
    """
    # 쿠키에서 access_token 읽기
    access_token = request.cookies.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="액세스 토큰이 없습니다.",
        )

    try:
        payload = JWTHandler.decode_token(access_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 토큰입니다.",
            )

        return UUID(user_id)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰 검증에 실패했습니다.",
        ) from e
