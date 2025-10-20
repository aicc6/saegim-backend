"""
OpenAI API 호출 유틸리티 함수
"""

import asyncio
import logging
import os
from typing import Any, cast

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

logger = logging.getLogger(__name__)


class OpenAIConfig:
    """OpenAI 설정 클래스"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        default_model: str = "gpt-4o-mini",
        temperature: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_model = default_model or os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5")
        self.temperature = temperature

        if not self.api_key:
            raise ValueError(
                "OpenAI API 키가 설정되지 않았습니다. OPENAI_API_KEY 환경변수를 확인하세요."
            )


class OpenAIClient:
    """OpenAI 클라이언트 래퍼 클래스"""

    def __init__(self, config: OpenAIConfig | None = None):
        self.config = config or OpenAIConfig()
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        채팅 완성 API 호출

        Args:
            messages: 대화 메시지 리스트
            model: 사용할 모델 (기본값: config의 default_model)
            temperature: 창의성 수준 (0.0~2.0, 기본값: config의 temperature)
            max_completion_tokens: 최대 완성 토큰 수
            **kwargs: 추가 파라미터

        Returns:
            API 응답 데이터
        """
        try:
            # gpt-5 모델은 temperature=1만 지원하므로 기본값일 때는 파라미터를 생략
            response = cast(
                ChatCompletion,
                self.client.chat.completions.create(
                    model=model or self.config.default_model,
                    messages=messages,
                    max_completion_tokens=max_completion_tokens,
                    temperature=(
                        temperature
                        if temperature is not None
                        else self.config.temperature
                    ),
                    **kwargs,
                ),
            )

            return {
                "id": response.id,
                "content": response.choices[0].message.content,
                "model": response.model,
                "created": response.created,
                "usage": {
                    "completion_tokens": (
                        response.usage.completion_tokens if response.usage else 0
                    ),
                    "prompt_tokens": (
                        response.usage.prompt_tokens if response.usage else 0
                    ),
                    "total_tokens": (
                        response.usage.total_tokens if response.usage else 0
                    ),
                },
                "finish_reason": response.choices[0].finish_reason,
                "role": response.choices[0].message.role,
            }

        except RateLimitError as e:
            logger.error(f"OpenAI API 요청 한도 초과: {str(e)}")
            raise
        except APITimeoutError as e:
            logger.error(f"OpenAI API 타임아웃: {str(e)}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI API 연결 오류: {str(e)}")
            raise
        except APIStatusError as e:
            logger.error(f"OpenAI API 상태 오류 (HTTP {e.status_code}): {str(e)}")
            raise
        except APIError as e:
            logger.error(f"OpenAI API 오류: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"OpenAI chat completion 예상치 못한 오류: {str(e)}")
            raise

    async def create_completion_async(self, **kwargs: Any) -> dict[str, Any]:
        """
        통합 비동기 완성 API 호출

        Args:
            **kwargs: OpenAI API 파라미터

        Returns:
            API 응답 데이터

        Raises:
            AIGenerationFailedException: OpenAI API 타임아웃 또는 기타 오류
        """
        try:
            response = cast(
                ChatCompletion,
                await self.async_client.chat.completions.create(**kwargs),
            )
            return {
                "id": response.id,
                "content": response.choices[0].message.content,
                "model": response.model,
                "created": response.created,
                "usage": {
                    "completion_tokens": (
                        response.usage.completion_tokens if response.usage else 0
                    ),
                    "prompt_tokens": (
                        response.usage.prompt_tokens if response.usage else 0
                    ),
                    "total_tokens": (
                        response.usage.total_tokens if response.usage else 0
                    ),
                },
                "finish_reason": response.choices[0].finish_reason,
                "role": response.choices[0].message.role,
            }
        except asyncio.TimeoutError:
            logger.error("OpenAI API 타임아웃 발생")
            from app.exceptions.ai import AIGenerationFailedException

            raise AIGenerationFailedException("OpenAI API 타임아웃")
        except Exception as e:
            logger.error(f"OpenAI API 오류: {e}")
            from app.exceptions.ai import AIGenerationFailedException

            raise AIGenerationFailedException(f"OpenAI API 오류: {str(e)}")

    async def async_chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        비동기 채팅 완성 API 호출 (타임아웃 처리 개선)
        """
        try:
            # gpt-5 모델은 temperature=1만 지원하므로 기본값일 때는 파라미터를 생략
            response = cast(
                ChatCompletion,
                await self.async_client.chat.completions.create(
                    model=model or self.config.default_model,
                    messages=messages,
                    max_completion_tokens=max_completion_tokens,
                    temperature=(
                        temperature
                        if temperature is not None
                        else self.config.temperature
                    ),
                    **kwargs,
                ),
            )

            return {
                "id": response.id,
                "content": response.choices[0].message.content,
                "model": response.model,
                "created": response.created,
                "usage": {
                    "completion_tokens": (
                        response.usage.completion_tokens if response.usage else 0
                    ),
                    "prompt_tokens": (
                        response.usage.prompt_tokens if response.usage else 0
                    ),
                    "total_tokens": (
                        response.usage.total_tokens if response.usage else 0
                    ),
                },
                "finish_reason": response.choices[0].finish_reason,
                "role": response.choices[0].message.role,
            }

        except RateLimitError as e:
            logger.error(f"OpenAI API 요청 한도 초과: {str(e)}")
            raise
        except APITimeoutError as e:
            logger.error(f"OpenAI API 타임아웃: {str(e)}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI API 연결 오류: {str(e)}")
            raise
        except APIStatusError as e:
            logger.error(f"OpenAI API 상태 오류 (HTTP {e.status_code}): {str(e)}")
            raise
        except APIError as e:
            logger.error(f"OpenAI API 오류: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"OpenAI async chat completion 예상치 못한 오류: {str(e)}")
            raise

    def stream_chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        **kwargs: Any,
    ):
        """
        스트리밍 채팅 완성 API 호출
        """
        try:
            # gpt-5 모델은 temperature=1만 지원하므로 기본값일 때는 파라미터를 생략
            stream = self.client.chat.completions.create(
                model=model or self.config.default_model,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                stream=True,
                temperature=(
                    temperature if temperature is not None else self.config.temperature
                ),
                **kwargs,
            )

            for chunk in stream:
                if (
                    chunk.choices
                    and len(chunk.choices) > 0
                    and chunk.choices[0].delta.content is not None
                ):
                    yield chunk.choices[0].delta.content

        except RateLimitError as e:
            logger.error(f"OpenAI API 요청 한도 초과: {str(e)}")
            raise
        except APITimeoutError as e:
            logger.error(f"OpenAI API 타임아웃: {str(e)}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI API 연결 오류: {str(e)}")
            raise
        except APIStatusError as e:
            logger.error(f"OpenAI API 상태 오류 (HTTP {e.status_code}): {str(e)}")
            raise
        except APIError as e:
            logger.error(f"OpenAI API 오류: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"OpenAI stream chat completion 예상치 못한 오류: {str(e)}")
            raise

    async def async_stream_chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        **kwargs: Any,
    ):
        """
        비동기 스트리밍 채팅 완성 API 호출 (타임아웃 처리 개선)
        """
        try:
            stream = await self.async_client.chat.completions.create(
                model=model or self.config.default_model,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                stream=True,
                temperature=(
                    temperature if temperature is not None else self.config.temperature
                ),
                **kwargs,
            )

            async for chunk in stream:
                if (
                    chunk.choices
                    and len(chunk.choices) > 0
                    and chunk.choices[0].delta.content is not None
                ):
                    yield chunk.choices[0].delta.content

        except RateLimitError as e:
            logger.error(f"OpenAI API 요청 한도 초과: {str(e)}")
            raise
        except APITimeoutError as e:
            logger.error(f"OpenAI API 타임아웃: {str(e)}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI API 연결 오류: {str(e)}")
            raise
        except APIStatusError as e:
            logger.error(f"OpenAI API 상태 오류 (HTTP {e.status_code}): {str(e)}")
            raise
        except APIError as e:
            logger.error(f"OpenAI API 오류: {str(e)}")
            raise
        except Exception as e:
            logger.error(
                f"OpenAI async stream chat completion 예상치 못한 오류: {str(e)}"
            )
            raise


# 전역 클라이언트 인스턴스
_global_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """전역 OpenAI 클라이언트 인스턴스 반환"""
    global _global_client
    if _global_client is None:
        _global_client = OpenAIClient()
    return _global_client


# 편의 함수들
def simple_chat(
    message: str, model: str | None = None, temperature: float | None = None
) -> str:
    """간단한 채팅 API 호출"""
    client = get_openai_client()
    messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": message}]
    response = client.chat_completion(messages, model=model, temperature=temperature)
    return response["content"]


async def simple_async_chat(
    message: str, model: str | None = None, temperature: float | None = None
) -> str:
    """간단한 비동기 채팅 API 호출"""
    client = get_openai_client()
    messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": message}]
    response = await client.async_chat_completion(
        messages, model=model, temperature=temperature
    )
    return response["content"]


async def handwriting_ocr_from_url(image_url: str) -> str:
    """
    GPT-5 Vision으로 이미지 URL의 손글씨를 OCR(텍스트 추출)합니다.
    """
    client = get_openai_client()
    response = await client.async_chat_completion(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "이 손글씨 이미지에 적힌 모든 문장을 가능한 한 빠짐없이 추출해서 그대로 반환해 주세요.",
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        model="gpt-5",  # Vision 인식 지원 모델명
        # temperature=0.0,
        max_completion_tokens=2048,
    )
    return response["content"]
