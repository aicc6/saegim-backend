"""
AI 텍스트 생성 서비스 (OpenAI API 사용)
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions.ai import (
    InvalidRequestException,
    SessionNotFoundException,
)
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import GetOriginalUserInputResponseData
from app.schemas.create_diary import CreateDiaryRequest
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class EmotionType(str, Enum):
    """감정 타입 (diary_ai.py에서 가져옴)"""

    HAPPINESS = "행복"
    SADNESS = "슬픔"
    ANGER = "화남"
    PEACE = "평온"
    UNREST = "불안"


class WritingStyle(str, Enum):
    """글 문체 타입"""

    POEM = "poem"  # 시
    SHORT_STORY = "short_story"  # 단편글


class ContentLength(str, Enum):
    """글귀 길이 타입"""

    SHORT = "short"  # 단문 (1-2문장)
    MEDIUM = "medium"  # 중문 (3-5문장)
    LONG = "long"  # 장문 (6-10문장)


class AIService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)

        import os

        from openai import AsyncOpenAI

        self._openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # 한국어 감정을 영어로 변환하는 매핑
        self.emotion_mapping = {
            "행복": "happy",
            "슬픔": "sad",
            "화남": "angry",
            "평온": "peaceful",
            "불안": "unrest",
        }

    def _convert_emotion_to_english(self, korean_emotion: str) -> str:
        """한국어 감정을 영어로 변환"""
        return self.emotion_mapping.get(korean_emotion, "peaceful")

    async def stream_ai_text(
        self,
        user_id: UUID,
        data: CreateDiaryRequest,
    ):
        """AI 텍스트 실시간 스트리밍 생성"""
        try:
            logger.info(f"AI 텍스트 스트리밍 시작: {data.prompt[:50]}...")

            # 세션 ID 생성/확인
            session_id = (
                getattr(data, "sessionId", None) or data.session_id or str(uuid.uuid4())
            )

            # 재생성 횟수 확인
            statement = (
                select(AIUsageLog)
                .where(AIUsageLog.session_id == session_id)
                .where(AIUsageLog.api_type == "integrated_analysis")
            )
            existing_logs = self._db.execute(statement).scalars().all()
            regeneration_count = len(existing_logs) + 1

            if regeneration_count > 5:
                error_data = {
                    "error": "재생성 횟수가 5회를 초과했습니다.",
                    "session_id": session_id,
                    "current_count": regeneration_count,
                }
                yield json.dumps(error_data, ensure_ascii=False)
                return

            # 초기 메타데이터 전송
            initial_data = {
                "type": "start",
                "session_id": session_id,
                "regeneration_count": regeneration_count,
            }
            yield json.dumps(initial_data, ensure_ascii=False)

            # 스트리밍으로 텍스트 생성
            collected_text = ""
            total_tokens = 0
            chunk_index = 0

            async for text_chunk in self._stream_complete_analysis(
                data.prompt, data.style, data.length
            ):
                if isinstance(text_chunk, dict) and "tokens_used" in text_chunk:
                    total_tokens = text_chunk["tokens_used"]
                    continue

                collected_text += text_chunk
                chunk_data = {
                    "type": "content",
                    "content": text_chunk,
                    "accumulated": collected_text,
                    "timestamp": int(time.time() * 1000),  # 서버 타임스탬프 추가
                    "chunk_index": chunk_index,  # 청크 순서 보장
                }
                chunk_index += 1
                yield json.dumps(chunk_data, ensure_ascii=False)

            # 완료 후 분석 결과 처리 (평문 텍스트)
            generated_text = collected_text.strip()

            # 생성된 텍스트에 대해 별도로 감정 분석과 키워드 추출
            try:
                # 통합 분석을 통한 감정 분석 및 키워드 추출
                analysis_result = await self._integrated_analysis(
                    data.prompt, data.style, data.length
                )
                emotion = analysis_result["emotion"]
                keywords = analysis_result["keywords"]
                logger.info(
                    f"스트리밍 후 감정 분석 완료: emotion='{emotion}', keywords={keywords}"
                )

            except Exception as e:
                logger.warning(f"스트리밍 후 분석 실패: {str(e)}")
                # Fallback: 키워드 기반 감정 분석
                emotion = self._analyze_emotion_from_keywords(data.prompt)
                keywords = data.prompt.split()[:5] if data.prompt else []
                logger.info(
                    f"Fallback 감정 분석: emotion='{emotion}', keywords={keywords}"
                )

            # 스트리밍 로그 저장
            ai_usage_log = AIUsageLog(
                user_id=user_id,
                api_type="integrated_analysis",
                session_id=session_id,
                request_data=data.model_dump(),
                response_data={
                    "ai_generated_text": generated_text,
                    "emotion": emotion,
                    "keywords": keywords,
                    "style": data.style,
                    "length": data.length,
                },
                tokens_used=total_tokens,
                regeneration_count=regeneration_count,
            )
            self._db.add(ai_usage_log)
            self._db.commit()

            # 완료 메타데이터 전송
            final_data = {
                "type": "complete",
                "emotion": emotion,
                "keywords": keywords,
                "generated_text": generated_text,
                "tokens_used": total_tokens,
                "session_id": session_id,
            }
            yield json.dumps(final_data, ensure_ascii=False)

        except Exception as e:
            logger.error(f"AI 텍스트 스트리밍 실패: {str(e)}")
            error_data = {
                "type": "error",
                "error": f"AI 텍스트 생성 중 오류가 발생했습니다: {str(e)}",
            }
            yield json.dumps(error_data, ensure_ascii=False)

    async def _stream_complete_analysis(self, prompt: str, style: str, length: str):
        """스트리밍으로 통합 분석 수행"""
        try:
            # 스타일 및 길이 매핑
            style_info = {
                "poem": {
                    "name": "시",
                    "desc": "시적이고 운율이 있는 표현으로, 은유와 상징을 사용",
                },
                "short_story": {
                    "name": "단편글",
                    "desc": "자연스럽고 따뜻한 문체로, 이야기하듯 편안하게",
                },
            }

            length_info = {
                "short": {"name": "단문", "desc": "1-2문장, 최대 50자 이내"},
                "medium": {"name": "중문", "desc": "3-5문장, 최대 150자 이내"},
                "long": {"name": "장문", "desc": "6-10문장, 최대 300자 이내"},
            }

            style_guide = style_info.get(
                style,
                {
                    "name": "단편글",
                    "desc": "자연스럽고 따뜻한 문체로 사용자의 감정을 잘 표현해주세요.",
                },
            )
            length_guide = length_info.get(length, {"name": "중문", "desc": "3-5문장"})

            system_message = f"""당신은 글에서 감정을 깊이 있게 분석하여 그 감정을 풍부하고 감성적으로 표현하는 전문 작가입니다.

주어진 키워드나 텍스트를 바탕으로 감정의 깊이와 복잡성을 잘 드러내는 글귀를 생성해주세요:

- 문체: {style_guide["name"]} ({style_guide["desc"]})
- 길이: {length_guide["name"]} ({length_guide["desc"]}) - 반드시 이 길이를 지켜주세요
- 감정의 미묘한 뉘앙스와 깊이를 표현하는 톤
- 사용자의 감정을 그대로 받아들이고 풍부하게 확장하여 표현
- 위로보다는 감정 자체의 아름다움과 복잡성을 드러내는 방식
- 시의 시풍은 [현대 한국 산문시풍, 한국시조, 당나라시풍, 하이쿠, 영국/프랑스/러시아 시풍] 중에서 랜덤하게 하나를 선택해 작성
- 단편글은 소설의 한 장면을 묘사하듯이 작성, 문단과 문장 길이와 구조에 변화를 주어 리듬감 있게 작성, 화자는 1인칭 시점으로 작성
- 글귀는 독립적인 하나의 완결된 작품처럼 느껴지도록 작성
- 중요: 글귀는 반드시 요청된 길이 제한 내에서 생성해야 합니다

생성된 글귀만 답해주세요. 다른 설명이나 JSON 형식은 사용하지 마세요."""

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"사용자 입력: {prompt}"},
            ]

            # 재시도 로직 추가
            max_retries = 3
            retry_delay = 1  # 초기 지연 시간 (초)

            for attempt in range(max_retries):
                try:
                    stream = await self._openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        max_completion_tokens=500,
                        stream=True,
                    )

                    chunk_count = 0
                    total_content = ""

                    async for chunk in stream:
                        chunk_count += 1
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            total_content += content

                            yield content

                    # 성공적으로 완료되면 루프 종료
                    break

                except Exception as e:
                    error_message = str(e)
                    logger.warning(
                        f"OpenAI API 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_message}"
                    )

                    # 마지막 시도이거나 재시도할 수 없는 오류인 경우
                    if (
                        attempt == max_retries - 1
                        or "rate limit" not in error_message.lower()
                    ):
                        logger.error(f"스트리밍 AI 분석 실패: {error_message}")
                        raise

                    # 재시도 가능한 오류인 경우 지연 후 재시도
                    await asyncio.sleep(retry_delay * (2**attempt))  # 지수 백오프
                    logger.info(f"재시도 중... ({retry_delay * (2**attempt)}초 후)")

        except Exception as e:
            logger.error(f"스트리밍 AI 분석 실패: {str(e)}")
            raise

    def get_regeneration_status(self, session_id: str) -> dict[str, Any]:
        """
        특정 세션의 재생성 횟수 정보 조회

        Args:
            session_id: 세션 ID

        Returns:
            Dict: 재생성 횟수 정보
        """
        try:
            statement = (
                select(AIUsageLog)
                .where(AIUsageLog.session_id == session_id)
                .where(AIUsageLog.api_type == "integrated_analysis")
            )

            existing_logs = self._db.execute(statement).scalars().all()
            current_count = len(existing_logs)

            return {
                "session_id": session_id,
                "current_count": current_count,
                "max_count": 5,
                "remaining_count": max(0, 5 - current_count),
                "can_regenerate": current_count < 5,
                "is_limit_reached": current_count >= 5,
            }

        except Exception as e:
            logger.error(f"재생성 상태 조회 실패: {str(e)}")
            raise SessionNotFoundException(session_id=session_id) from e

    async def get_original_user_input(
        self,
        user_id: UUID,
        session_id: str,
    ):
        """세션ID로 원본 사용자 입력 조회"""
        statement = (
            select(AIUsageLog)
            .where(AIUsageLog.session_id == session_id)
            .where(AIUsageLog.user_id == user_id)
            .where(AIUsageLog.api_type == "integrated_analysis")
            .order_by(AIUsageLog.created_at.asc())
            .limit(1)
        )

        result = self._db.execute(statement).scalar_one_or_none()
        if result and result.request_data:
            original_input = (
                result.request_data.get("prompt")
                if result.request_data.get("prompt", "").strip()
                else None
            )
            if original_input is not None:
                return GetOriginalUserInputResponseData(original_input=original_input)
        raise

    def test_db_connection(self) -> dict[str, Any]:
        """
        DB 연결 상태 테스트

        Returns:
            Dict: DB 연결 상태 정보
        """
        try:
            # 간단한 쿼리 실행
            statement = select(func.count()).select_from(AIUsageLog)
            result = self._db.execute(statement).scalar()

            return {
                "status": "success",
                "message": "DB 연결 정상",
                "total_logs": result,
                "db_session": str(type(self._db)),
                "timestamp": str(datetime.now()),
            }

        except Exception as e:
            logger.error(f"DB 연결 테스트 실패: {str(e)}")

            return {
                "status": "error",
                "message": f"DB 연결 실패: {str(e)}",
                "error_type": type(e).__name__,
                "timestamp": str(datetime.now()),
            }

    def get_user_daily_stats(self, user_id: UUID) -> dict[str, Any]:
        """
        사용자의 일일 AI 사용 통계 조회

        Args:
            user_id: 사용자 ID

        Returns:
            Dict: 일일 AI 사용 통계
        """
        try:
            from datetime import datetime

            # 오늘 날짜 기준으로 조회
            today = datetime.now(UTC).date()

            statement = (
                select(AIUsageLog)
                .where(AIUsageLog.user_id == user_id)
                .where(AIUsageLog.api_type == "integrated_analysis")
                .where(func.date(AIUsageLog.created_at) == today)
            )

            logs = self._db.execute(statement).scalars().all()

            # 세션별 통계
            session_stats = {}
            total_tokens = 0
            total_requests = len(logs)

            for log in logs:
                session_id = str(log.session_id)
                if session_id not in session_stats:
                    session_stats[session_id] = {
                        "session_id": session_id,
                        "request_count": 0,
                        "tokens_used": 0,
                        "first_request": log.created_at,
                        "last_request": log.created_at,
                    }

                session_stats[session_id]["request_count"] += 1
                session_stats[session_id]["tokens_used"] += log.tokens_used or 0
                session_stats[session_id]["last_request"] = max(
                    session_stats[session_id]["last_request"], log.created_at
                )

                total_tokens += log.tokens_used or 0

            return {
                "user_id": user_id,
                "date": today.isoformat(),
                "total_sessions": len(session_stats),
                "total_requests": total_requests,
                "total_tokens_used": total_tokens,
                "average_tokens_per_request": (
                    round(total_tokens / total_requests, 2) if total_requests > 0 else 0
                ),
                "sessions": list(session_stats.values()),
            }

        except Exception as e:
            logger.error(f"사용자 일일 통계 조회 실패: {str(e)}")
            raise InvalidRequestException(
                detail=f"사용자 통계 조회 중 오류가 발생했습니다: {str(e)}",
                field="user_id",
            ) from e

    # validate_request 메소드 제거됨 - Pydantic 모델에서 자동 검증 처리

    async def stream_regenerate_by_session_id(self, user_id: UUID, session_id: str):
        """세션 ID로 이전 요청 정보를 가져와서 스트리밍 재생성"""
        try:
            logger.info(
                f"재생성 스트리밍 시작: session_id={session_id}, user_id={user_id}"
            )

            # 해당 세션의 가장 최근 로그 조회
            statement = (
                select(AIUsageLog)
                .where(AIUsageLog.session_id == session_id)
                .where(AIUsageLog.user_id == user_id)
                .where(AIUsageLog.api_type == "integrated_analysis")
                .order_by(AIUsageLog.created_at.desc())
                .limit(1)
            )

            result = self._db.execute(statement)
            last_log = result.scalar_one_or_none()

            if not last_log:
                error_data = {
                    "type": "error",
                    "error": f"세션 ID {session_id}에 해당하는 로그를 찾을 수 없습니다.",
                }
                yield json.dumps(error_data, ensure_ascii=False)
                return

            # 현재 세션의 총 재생성 횟수 확인 (5회 제한)
            session_logs_count = (
                self._db.execute(
                    select(func.count(AIUsageLog.id))
                    .where(AIUsageLog.session_id == session_id)
                    .where(AIUsageLog.api_type == "integrated_analysis")
                ).scalar()
                or 0
            )

            if session_logs_count >= 5:
                yield json.dumps(
                    {
                        "type": "error",
                        "error": "재생성 횟수가 5회를 초과했습니다.",
                        "session_id": session_id,
                        "current_count": session_logs_count,
                    },
                    ensure_ascii=False,
                )
                return

            # 이전 요청 데이터 복원
            import json as json_lib

            original_request_data = (
                json_lib.loads(last_log.request_data)
                if isinstance(last_log.request_data, str)
                else last_log.request_data
            )
            original_request = CreateDiaryRequest(**original_request_data)

            # 새로운 재생성 횟수로 설정
            new_regeneration_count = session_logs_count + 1

            # 초기 메타데이터 전송
            yield json.dumps(
                {
                    "type": "start",
                    "session_id": session_id,
                    "regeneration_count": new_regeneration_count,
                },
                ensure_ascii=False,
            )

            # 스트리밍으로 텍스트 생성 (기존 stream_ai_text와 동일한 로직)
            collected_text = ""
            total_tokens = 0
            chunk_index = 0

            async for text_chunk in self._stream_complete_analysis(
                original_request.prompt, original_request.style, original_request.length
            ):
                if isinstance(text_chunk, dict) and "tokens_used" in text_chunk:
                    total_tokens = text_chunk["tokens_used"]
                    continue

                collected_text += text_chunk
                chunk_data = {
                    "type": "content",
                    "content": text_chunk,
                    "accumulated": collected_text,
                    "timestamp": int(time.time() * 1000),
                    "chunk_index": chunk_index,
                }
                chunk_index += 1
                yield json.dumps(chunk_data, ensure_ascii=False)

            # 완료 후 분석 결과 처리
            generated_text = collected_text.strip()

            # 생성된 텍스트에 대해 별도로 감정 분석과 키워드 추출
            try:
                # 통합 분석을 통한 감정 분석 및 키워드 추출
                analysis_result = await self._integrated_analysis(
                    original_request.prompt,
                    original_request.style,
                    original_request.length,
                )
                emotion = analysis_result["emotion"]
                keywords = analysis_result["keywords"]
                logger.info(
                    f"재생성 후 감정 분석 완료: emotion='{emotion}', keywords={keywords}"
                )

            except Exception as e:
                logger.warning(f"재생성 스트리밍 후 분석 실패: {str(e)}")
                # Fallback: 키워드 기반 감정 분석
                emotion = self._analyze_emotion_from_keywords(original_request.prompt)
                keywords = (
                    original_request.prompt.split()[:5]
                    if original_request.prompt
                    else []
                )
                logger.info(
                    f"재생성 Fallback 감정 분석: emotion='{emotion}', keywords={keywords}"
                )

            # 재생성 스트리밍 로그 저장
            ai_usage_log = AIUsageLog(
                user_id=user_id,
                api_type="integrated_analysis",
                session_id=session_id,
                request_data=original_request_data,
                response_data={
                    "ai_generated_text": generated_text,
                    "emotion": emotion,
                    "keywords": keywords,
                    "style": original_request.style,
                    "length": original_request.length,
                },
                tokens_used=total_tokens,
                regeneration_count=new_regeneration_count,
            )
            self._db.add(ai_usage_log)
            self._db.commit()

            # 완료 메타데이터 전송
            yield json.dumps(
                {
                    "type": "complete",
                    "emotion": emotion,
                    "keywords": keywords,
                    "generated_text": generated_text,
                    "tokens_used": total_tokens,
                    "session_id": session_id,
                    "regeneration_count": new_regeneration_count,
                },
                ensure_ascii=False,
            )

            logger.info(
                f"재생성 스트리밍 완료: session_id={session_id}, tokens={total_tokens}"
            )

        except Exception as e:
            logger.error(
                f"재생성 스트리밍 실패: session_id={session_id}, error={str(e)}"
            )
            error_data = {
                "type": "error",
                "error": f"재생성 중 오류가 발생했습니다: {str(e)}",
            }
            yield json.dumps(error_data, ensure_ascii=False)

    def _analyze_emotion_from_keywords(self, text: str) -> str:
        """키워드 기반 감정 분석 (AI 실패 시 fallback)"""
        text_lower = text.lower()
        logger.info(f"키워드 기반 분석 시작: '{text}' -> '{text_lower}'")

        # 화남 키워드
        anger_keywords = [
            "화가 난다",
            "짜증",
            "분노",
            "억울",
            "격분",
            "열받다",
            "빡친다",
            "화나다",
            "화남",
        ]
        anger_matches = [keyword for keyword in anger_keywords if keyword in text_lower]
        if anger_matches:
            logger.info(f"화남 키워드 매칭: {anger_matches}")
            return "angry"

            # 슬픔 키워드
        sadness_keywords = [
            "슬프다",
            "우울",
            "눈물",
            "아쉽다",
            "서운",
            "울고 싶다",
            "힘들다",
            "슬픔",
        ]
        sadness_matches = [
            keyword for keyword in sadness_keywords if keyword in text_lower
        ]
        if sadness_matches:
            logger.info(f"슬픔 키워드 매칭: {sadness_matches}")
            return "sad"

        # 불안 키워드
        anxiety_keywords = [
            "걱정",
            "불안",
            "두렵다",
            "초조",
            "긴장",
            "무서워",
            "떨린다",
            "조마조마",
            "불안정",
        ]
        anxiety_matches = [
            keyword for keyword in anxiety_keywords if keyword in text_lower
        ]
        if anxiety_matches:
            logger.info(f"불안 키워드 매칭: {anxiety_matches}")
            return "unrest"

        # 행복 키워드
        happiness_keywords = [
            "기쁘다",
            "행복",
            "좋다",
            "즐겁다",
            "신나다",
            "뿌듯하다",
            "웃음",
            "행복하다",
        ]
        happiness_matches = [
            keyword for keyword in happiness_keywords if keyword in text_lower
        ]
        if happiness_matches:
            logger.info(f"행복 키워드 매칭: {happiness_matches}")
            return "happy"

        # 평온 키워드
        peaceful_keywords = [
            "편안하다",
            "차분하다",
            "안정적",
            "조용하다",
            "평화롭다",
            "고요하다",
            "만족",
        ]
        peaceful_matches = [
            keyword for keyword in peaceful_keywords if keyword in text_lower
        ]
        if peaceful_matches:
            logger.info(f"평온 키워드 매칭: {peaceful_matches}")
            return "peaceful"

        # 기본값: 평온
        logger.info("키워드 매칭 없음, 기본값 peaceful 반환")
        return "peaceful"

    def _has_strong_emotion_keywords(self, text: str) -> bool:
        """강한 감정 키워드가 있는지 확인"""
        text_lower = text.lower()

        # 모든 강한 감정 키워드 수집
        strong_keywords = [
            "화가 난다",
            "짜증",
            "분노",
            "억울",
            "격분",
            "열받다",
            "빡친다",
            "화나다",
            "화남",
            "슬프다",
            "우울",
            "눈물",
            "아쉽다",
            "서운",
            "울고 싶다",
            "힘들다",
            "슬픔",
            "걱정",
            "불안",
            "두렵다",
            "초조",
            "긴장",
            "무서워",
            "떨린다",
            "조마조마",
            "불안정",
            "기쁘다",
            "행복",
            "좋다",
            "즐겁다",
            "신나다",
            "뿌듯하다",
            "웃음",
            "행복하다",
        ]

        has_strong_keyword = any(keyword in text_lower for keyword in strong_keywords)
        logger.info(f"강한 감정 키워드 감지: {has_strong_keyword}")
        return has_strong_keyword

    async def _integrated_analysis(
        self, prompt: str, style: str, length: str
    ) -> dict[str, Any]:
        """통합 분석 수행 (감정 분석 및 키워드 추출)"""
        try:
            analysis_prompt = f"""
<task>
주어진 사용자 입력을 분석하여 감정 분석과 키워드 추출을 수행해주세요.

<user_input>
{prompt}
</user_input>

<analysis_requirements>
1. 감정 분석: 다음 5가지 감정 중 하나를 선택해주세요
   - 행복: 기쁨, 만족, 즐거움을 나타내는 감정
   - 슬픔: 우울, 서운함, 아쉬움을 나타내는 감정
   - 화남: 분노, 짜증, 억울함을 나타내는 감정
   - 평온: 차분함, 안정감, 편안함을 나타내는 감정
   - 불안: 걱정, 두려움, 긴장을 나타내는 감정

2. 키워드 추출: 사용자 입력의 핵심 의미를 담은 키워드 3-5개를 추출해주세요
   - 사용자가 직접 언급한 단어가 아니더라도 핵심 의미를 담은 키워드면 좋습니다
   - 감정, 상황, 대상, 행동 등을 포함한 의미있는 키워드를 선택해주세요
</analysis_requirements>

<response_format>
반드시 다음 JSON 형식으로만 답해주세요:
{{"emotion": "감정명", "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]}}
</response_format>
</task>
"""

            # 재시도 로직 추가
            max_retries = 3
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    response = await self._openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": analysis_prompt}],
                        max_completion_tokens=200,
                        temperature=0.3,  # 일관성 있는 분석을 위해 낮은 temperature 사용
                    )

                    content = response.choices[0].message.content.strip()
                    logger.info(f"통합 분석 원본 응답: {content}")

                    # JSON 파싱 시도
                    try:
                        import json as json_lib

                        # JSON 블록 추출 시도
                        if "```json" in content:
                            content = (
                                content.split("```json")[1].split("```")[0].strip()
                            )
                        elif "{" in content and "}" in content:
                            start = content.find("{")
                            end = content.rfind("}") + 1
                            content = content[start:end]

                        analysis_result = json_lib.loads(content)

                        # 결과 검증
                        if (
                            "emotion" in analysis_result
                            and "keywords" in analysis_result
                        ):
                            emotion = analysis_result["emotion"]
                            keywords = analysis_result["keywords"]

                            # 감정 검증
                            valid_emotions = ["행복", "슬픔", "화남", "평온", "불안"]
                            if emotion not in valid_emotions:
                                logger.warning(
                                    f"잘못된 감정: {emotion}, 평온으로 기본 설정"
                                )
                                emotion = "평온"

                            # 한국어 감정을 영어로 변환
                            english_emotion = self._convert_emotion_to_english(emotion)
                            logger.info(f"감정 변환: {emotion} -> {english_emotion}")

                            # 키워드 검증 및 정리
                            if isinstance(keywords, list):
                                keywords = [
                                    str(kw).strip()
                                    for kw in keywords
                                    if str(kw).strip()
                                ][
                                    :5
                                ]  # 최대 5개
                            else:
                                keywords = []

                            if not keywords:  # 키워드가 없으면 fallback
                                keywords = prompt.split()[:3] if prompt else ["감정"]

                            logger.info(
                                f"통합 분석 완료: emotion={emotion}->{english_emotion}, keywords={keywords}"
                            )
                            return {
                                "emotion": english_emotion,
                                "keywords": keywords,
                            }  # 영어 감정 반환

                        else:
                            raise ValueError("응답에 필수 필드가 없습니다")

                    except (
                        json_lib.JSONDecodeError,
                        ValueError,
                        KeyError,
                    ) as parse_error:
                        logger.warning(
                            f"JSON 파싱 실패 ({attempt + 1}/{max_retries}): {parse_error}"
                        )
                        if attempt == max_retries - 1:
                            raise parse_error

                except Exception as e:
                    error_message = str(e)
                    logger.warning(
                        f"통합 분석 API 호출 실패 ({attempt + 1}/{max_retries}): {error_message}"
                    )

                    if (
                        attempt == max_retries - 1
                        or "rate limit" not in error_message.lower()
                    ):
                        raise

                    # 재시도 가능한 오류인 경우 지연 후 재시도
                    await asyncio.sleep(retry_delay * (2**attempt))

            # 모든 재시도가 실패한 경우 (이 라인에 도달하면 안 되지만 타입 체커를 위해)
            raise Exception("모든 재시도가 실패했습니다")

        except Exception as e:
            logger.error(f"통합 분석 실패: {str(e)}")
            # Fallback: 키워드 기반 분석
            emotion = self._analyze_emotion_from_keywords(prompt)
            keywords = prompt.split()[:3] if prompt else ["감정"]
            # fallback 감정도 영어로 변환
            english_emotion = self._convert_emotion_to_english(emotion)
            logger.info(
                f"Fallback 통합 분석: emotion={emotion}->{english_emotion}, keywords={keywords}"
            )
            return {"emotion": english_emotion, "keywords": keywords}
