"""
HTTP 클라이언트 유틸리티
httpx 중복 사용 패턴 제거 및 표준화된 HTTP 요청 제공
"""

import logging
from typing import Any

import httpx
from fastapi import status

from app.core.errors import ErrorFactory

logger = logging.getLogger(__name__)


class HttpClient:
    """표준화된 HTTP 클라이언트 래퍼"""

    def __init__(self, timeout: float = 30.0):
        """
        HTTP 클라이언트 초기화

        Args:
            timeout: 요청 타임아웃 (초)
        """
        self.timeout = timeout

    async def post_json(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
        expected_status: int = status.HTTP_200_OK,
    ) -> dict[str, Any]:
        """POST JSON 요청 실행

        Args:
            url: 요청 URL
            data: POST 데이터
            headers: 요청 헤더
            expected_status: 예상 상태 코드

        Returns:
            Dict: JSON 응답 데이터

        Raises:
            HTTPException: 요청 실패 시
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=data, headers=headers)

                if response.status_code != expected_status:
                    error_detail = self._extract_error_detail(response)
                    logger.error(
                        f"POST request failed. URL: {url}, "
                        f"Status: {response.status_code}, Details: {error_detail}"
                    )
                    raise ErrorFactory.bad_request(
                        f"HTTP 요청이 실패했습니다: {error_detail}",
                        {"url": url, "status_code": response.status_code},
                    )

                return response.json()

        except httpx.TimeoutException as e:
            logger.error(f"Request timeout for URL: {url}")
            raise ErrorFactory.internal_error("요청 시간 초과") from e
        except httpx.RequestError as e:
            logger.error(f"Request error for URL {url}: {e}")
            raise ErrorFactory.internal_error("네트워크 요청 오류") from e

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        expected_status: int = status.HTTP_200_OK,
    ) -> dict[str, Any]:
        """GET JSON 요청 실행

        Args:
            url: 요청 URL
            headers: 요청 헤더
            expected_status: 예상 상태 코드

        Returns:
            Dict: JSON 응답 데이터

        Raises:
            HTTPException: 요청 실패 시
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code != expected_status:
                    error_detail = self._extract_error_detail(response)
                    logger.error(
                        f"GET request failed. URL: {url}, "
                        f"Status: {response.status_code}, Details: {error_detail}"
                    )
                    raise ErrorFactory.bad_request(
                        f"HTTP 요청이 실패했습니다: {error_detail}",
                        {"url": url, "status_code": response.status_code},
                    )

                return response.json()

        except httpx.TimeoutException:
            logger.error(f"Request timeout for URL: {url}")
            raise ErrorFactory.internal_error("요청 시간 초과")
        except httpx.RequestError as e:
            logger.error(f"Request error for URL {url}: {e}")
            raise ErrorFactory.internal_error("네트워크 요청 오류")

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """응답에서 에러 세부사항 추출

        Args:
            response: HTTP 응답 객체

        Returns:
            str: 에러 세부사항
        """
        try:
            if response.content:
                error_data = response.json()
                return str(error_data)
            else:
                return "No error details available"
        except Exception:
            return f"Status {response.status_code}: {response.text}"


# 전역 HTTP 클라이언트 인스턴스
http_client = HttpClient()
