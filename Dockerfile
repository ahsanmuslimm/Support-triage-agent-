# Support Triage Agent - Production Dockerfile
# Multi-stage build for Railway deployment
# Handles uv workspace structure with local package dependencies

FROM python:3.12-slim as builder

WORKDIR /build

# Install build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy entire source tree to handle local dependencies
COPY . /build/

# Install dependencies without trying to use uv workspace
# Pin all versions to avoid resolution issues in Docker
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    sqlalchemy[asyncio]==2.0.23 \
    cryptography==41.0.7 \
    langdetect==1.0.9 \
    httpx==0.24.1 \
    python-multipart==0.0.6 \
    redis==5.0.1 \
    alembic==1.12.1 \
    "psycopg[binary]>=3.1" \
    sentence-transformers==2.2.2 \
    scikit-learn==1.3.2 \
    numpy==1.24.3 \
    structlog==24.1.0 \
    opentelemetry-api==1.21.0 \
    opentelemetry-sdk==1.21.0 \
    opentelemetry-exporter-otlp==0.42b0 \
    python-json-logger==2.0.7 \
    langgraph==0.2.0 \
    langchain-core==0.2.0 \
    litellm==1.30.0 \
    rank-bm25==0.2.2 \
    qdrant-client==1.9.0 \
    tiktoken==0.7.0 \
    transformers==4.30.0 \
    asyncpg==0.29.0

# Final runtime image
FROM python:3.12-slim

WORKDIR /app

# Install only runtime essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python site-packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY services/api/src/triage /app/triage
COPY packages/py_core/py_core /app/py_core

# Set environment
ENV PYTHONPATH=/app:$PYTHONPATH \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI with correct module path
CMD ["uvicorn", "triage.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
