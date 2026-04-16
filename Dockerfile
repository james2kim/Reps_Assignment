FROM python:3.13-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps (separate layer for caching)
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    "uvicorn[standard]>=0.30.0" \
    pydantic>=2.0 \
    pydantic-settings>=2.0 \
    anthropic>=0.40.0 \
    sqlalchemy>=2.0 \
    psycopg2-binary>=2.9 \
    python-dotenv>=1.0.0 \
    sentence-transformers>=3.0.0

# Copy app code + data
COPY backend/ backend/
COPY data/ data/

# Port Cloud Run expects
EXPOSE 8080

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
