# Support Triage Agent - Production Dockerfile
# Simplified for Railway deployment - minimal dependencies

FROM python:3.12-slim

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies using pip (no uv complexity)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install FastAPI and core dependencies directly
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    sqlalchemy[asyncio]==2.0.23 \
    pydantic==2.5.0 \
    psycopg[binary]==3.1.13 \
    redis==5.0.1 \
    httpx==0.24.1 \
    python-multipart==0.0.6 \
    langdetect==1.0.9 \
    alembic==1.12.1 \
    structlog==23.2.0 \
    langgraph==0.2.0 \
    langchain-core==0.2.0 \
    litellm==1.30.0 \
    sentence-transformers==2.2.2 \
    scikit-learn==1.3.2 \
    numpy==1.24.3 \
    rank-bm25==0.2.2 \
    qdrant-client==1.9.0 \
    tiktoken==0.7.0 \
    transformers==4.30.2

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:$PYTHONPATH" \
    PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "services.api.src.triage.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
