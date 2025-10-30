# 새김(Saegim) 백엔드 Dockerfile
# FastAPI + SQLAlchemy + PostgreSQL + Redis
# 멀티스테이지 빌드로 이미지 크기 최적화

# ==============================================================================
# Stage 1: Builder (의존성 설치 및 빌드)
# ==============================================================================
FROM python:3.11-slim AS builder

# 빌드 인수
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# 메타데이터
LABEL maintainer="새김 개발팀"
LABEL description="새김 감성 AI 다이어리 백엔드 API 서버"
LABEL version="1.0.0"

# 환경변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VENV_IN_PROJECT=1

# 시스템 의존성 설치 (빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉터리 설정
WORKDIR /app

# Python 의존성 파일만 먼저 복사 (Docker 레이어 캐싱 최적화)
COPY requirements.txt .

# Python 의존성 설치
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Stage 2: Runtime (실행 환경)
# ==============================================================================
FROM python:3.11-slim AS runtime

# 런타임 환경변수
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production

# 시스템 의존성 설치 (런타임용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 비root 사용자 생성 (보안 강화)
RUN groupadd --gid 1000 saegim && \
    useradd --uid 1000 --gid saegim --shell /bin/bash --create-home saegim

# 작업 디렉터리 설정
WORKDIR /app

# 빌더 스테이지에서 설치된 Python 패키지 복사
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 애플리케이션 코드 복사
COPY --chown=saegim:saegim . .

# .env 파일 복사 (환경변수 설정용)
COPY --chown=saegim:saegim .env* ./

# 로그 디렉터리 생성
RUN mkdir -p /app/logs && \
    chown -R saegim:saegim /app

# 사용자 권한 변경
USER saegim

# 포트 노출
EXPOSE 9000

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

# 시작 명령어
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1", "--log-level", "info"]
