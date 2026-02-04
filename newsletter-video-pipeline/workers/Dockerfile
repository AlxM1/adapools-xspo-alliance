# Newsletter Video Pipeline - Celery Workers Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY workers/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY workers/ ./workers/
COPY database/ ./database/

# Create non-root user
RUN useradd -m -u 1000 celery && \
    mkdir -p /app/logs /app/data && \
    chown -R celery:celery /app

USER celery

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A workers.celery_app inspect ping -d celery@$HOSTNAME || exit 1

CMD ["celery", "-A", "workers.celery_app", "worker", "-l", "info"]
