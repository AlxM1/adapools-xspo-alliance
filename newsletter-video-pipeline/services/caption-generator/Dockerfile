# Caption Generator Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create directories
RUN mkdir -p /app/logs /app/output

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FFMPEG_PATH=ffmpeg

EXPOSE 5011

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5011"]
