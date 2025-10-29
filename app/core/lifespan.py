"""
애플리케이션 생명주기 관리
FastAPI lifespan context manager
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import create_db_and_tables

logger = logging.getLogger(__name__)


async def preload_kcbert_model_background():
    """서버 부팅 시 백그라운드에서 KC-BERT 모델 미리 로딩"""
    try:
        from test_kcbert import initialize_predictor
        
        logger.info("🔥 서버 부팅 시 KC-BERT 모델 백그라운드 로딩 시작...")
        
        # 비동기적으로 모델 로딩 (다른 초기화 작업을 블로킹하지 않음)
        await asyncio.sleep(0.1)  # 다른 초기화 작업이 우선 완료되도록 잠시 대기
        
        success = initialize_predictor()
        if success:
            logger.info("🔥 서버 부팅 시 KC-BERT 모델 백그라운드 로딩 완료!")
        else:
            logger.warning("🔥 서버 부팅 시 KC-BERT 모델 백그라운드 로딩 실패")
            
    except Exception as e:
        logger.error(f"🔥 서버 부팅 시 KC-BERT 모델 백그라운드 로딩 중 오류: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 생명주기 관리

    시작 시:
    - 데이터베이스 테이블 생성
    - KC-BERT 모델 백그라운드 로딩
    - 필요한 초기화 작업 수행

    종료 시:
    - 연결 종료 및 리소스 정리
    """
    # === 시작 이벤트 ===
    logger.info("애플리케이션 시작 중...")

    try:
        # 데이터베이스 테이블 생성
        create_db_and_tables()
        logger.info("✅ 데이터베이스 테이블 생성 완료")
    except Exception as e:
        logger.warning(f"⚠️ 데이터베이스 연결 실패: {e}")
        logger.info("데이터베이스 없이 서버를 시작합니다.")

    # KC-BERT 모델 백그라운드 로딩 시작 (서버 시작을 블로킹하지 않음)
    asyncio.create_task(preload_kcbert_model_background())

    # 기타 초기화 작업 (필요 시 추가)
    # - Redis 연결 확인
    # - 외부 API 연결 테스트
    # - 백그라운드 태스크 시작

    logger.info("🚀 애플리케이션 시작 완료")

    yield  # 애플리케이션 실행

    # === 종료 이벤트 ===
    logger.info("🛑 애플리케이션 종료 중...")

    # 정리 작업 수행
    # - 데이터베이스 연결 종료
    # - Redis 연결 종료
    # - 백그라운드 태스크 중지
    # - 임시 파일 정리

    logger.info("✅ 애플리케이션 종료 완료")
