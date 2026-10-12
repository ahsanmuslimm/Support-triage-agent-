# Support Triage Agent - Production Dockerfile for Railway
# Lightweight build focused on FastAPI API server (no ML packages)

FROM python:3.12-slim as builder

WORKDIR /build

# Install build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements-production-lite.txt /build/

# Install dependencies from requirements file (no wheel building needed)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements-production-lite.txt

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
    CMD curl -f "http://localhost:${PORT:-8000}/health" || exit 1

# main.py exposes an app factory (create_app), not a module-level app
# Shell form so Railway's injected $PORT is expanded; exec keeps uvicorn as PID 1
CMD ["sh", "-c", "exec uvicorn triage.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
