"""
공개 API 라우터 (인증 불필요)
"""

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.core.config import get_settings

router = APIRouter(tags=["Public"])


@router.get("/image-proxy")
async def image_proxy(url: str = Query(..., description="프록시할 이미지 URL")):
    """이미지 CORS 문제 해결을 위한 프록시 엔드포인트 (인증 불필요)"""

    try:
        # 보안을 위해 허용된 도메인만 프록시
        settings = get_settings()
        allowed_domains = settings.image_proxy_domains

        parsed_url = urlparse(url)
        if parsed_url.hostname not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="허용되지 않는 도메인입니다",
            )

        # 이미지 요청
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            # Content-Type 헤더 확인
            content_type = response.headers.get(
                "content-type", "application/octet-stream"
            )
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="이미지 파일이 아닙니다",
                )

            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",  # 1시간 캐싱
                    "Access-Control-Allow-Origin": "*",
                },
            )

    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="이미지 로드 시간 초과",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"이미지 서버 오류: {str(e)}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이미지 프록시 오류",
        ) from e
