# ── PPKE Multi-Stage Dockerfile ──
# Build: docker build -t ppke .
# Run:   docker run -p 8000:8000 ppke
#
# Environment variables:
#   DATABASE_URL       — PostgreSQL URL (optional; SQLite default)
#   REDIS_URL          — Redis URL for caching + task queue
#   SENTRY_DSN         — Sentry error tracking DSN
#   PPKE_ENVIRONMENT   — "production", "staging", "development"
#   ANTHROPIC_API_KEY  — LLM provider keys
#   OPENAI_API_KEY
#   PPKE_LOG_FORMAT    — "json" or "text"

# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY ppke/ ppke/

# Install package with all optional dependencies
RUN pip install --no-cache-dir --prefix=/install ".[all]" && \
    pip install --no-cache-dir --prefix=/install \
    celery[redis] \
    redis \
    psycopg2-binary \
    prometheus-client \
    sentry-sdk[fastapi] \
    boto3 \
    google-cloud-storage

# ── Stage 2: Runtime ──
FROM python:3.11-slim AS runtime

# System dependencies: Tesseract OCR, ffmpeg (audio), poppler (PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    ffmpeg \
    poppler-utils \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
WORKDIR /app
COPY ppke/ ppke/
COPY pyproject.toml .

# Create non-root user
RUN groupadd -r ppke && useradd -r -g ppke -d /home/ppke -m ppke
RUN mkdir -p /home/ppke/.ppke /data && chown -R ppke:ppke /home/ppke /data

USER ppke

# Environment defaults
ENV PPKE_ENVIRONMENT=production \
    PPKE_LOG_FORMAT=json \
    PPKE_LOG_LEVEL=INFO \
    PPKE_METRICS_ENABLED=true \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_WORKERS=2 \
    HOME=/home/ppke

# Expose web port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command: run web server
CMD ["python", "-m", "uvicorn", "ppke.web.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--access-log"]
