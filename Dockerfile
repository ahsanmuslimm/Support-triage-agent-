# Support Triage Agent - Production Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install uv and sync dependencies for each workspace member
RUN pip install --no-cache-dir uv

# Install dependencies from each workspace member's pyproject.toml
RUN cd packages/py_core && pip install --no-cache-dir -e . || true
RUN cd services/api && pip install --no-cache-dir -e . || true
RUN cd services/triage_worker && pip install --no-cache-dir -e . || true
RUN cd services/knowledge_worker && pip install --no-cache-dir -e . || true

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:$PYTHONPATH" \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "services.api.src.triage.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
