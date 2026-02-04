"""
FastAPI application for API Gateway / Pipeline Orchestrator.

This is the main entry point for the newsletter-to-video pipeline.
It coordinates all backend services and provides a unified API.
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from .service import PipelineOrchestrator
from .models import (
    PipelineRequest,
    PipelineResponse,
    SystemHealthResponse,
)

# Global service instance
orchestrator: Optional[PipelineOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global orchestrator

    # Startup
    logger.info("Starting Newsletter Video Pipeline API Gateway...")

    orchestrator = PipelineOrchestrator(
        voice_service_url=os.getenv("GPU_VOICE_URL", "http://192.168.1.100:5002"),
        avatar_service_url=os.getenv("GPU_AVATAR_URL", "http://192.168.1.100:5003"),
        video_processor_url=os.getenv("VIDEO_PROCESSOR_URL", "http://localhost:5005"),
        social_publisher_url=os.getenv("SOCIAL_PUBLISHER_URL", "http://localhost:5006"),
        script_generator_url=os.getenv("SCRIPT_GENERATOR_URL", "http://localhost:5007"),
        output_dir=os.getenv("OUTPUT_DIR", "/data/videos/output"),
        temp_dir=os.getenv("TEMP_DIR", "/tmp/pipeline"),
    )

    await orchestrator.initialize()
    logger.info("API Gateway started successfully")

    yield

    # Shutdown
    logger.info("Shutting down API Gateway...")
    if orchestrator:
        await orchestrator.cleanup()
    logger.info("API Gateway stopped")


app = FastAPI(
    title="Newsletter Video Pipeline API",
    description="""
    # Newsletter-to-Video Automation Pipeline

    This API converts newsletters into engaging video content with:
    - AI-generated scripts
    - Voice cloning (your voice)
    - AI avatar video generation
    - Multi-platform optimization
    - Automated publishing to YouTube, TikTok, Instagram, and X

    ## Quick Start

    1. **POST /pipeline** - Submit a newsletter for full pipeline processing
    2. **GET /pipeline/{job_id}** - Check job status and get outputs
    3. **GET /health** - Check system health

    ## Architecture

    - **Linux VM**: API Gateway, Video Processor, Social Publisher, Script Generator
    - **Windows GPU Server (RTX 5090)**: Voice Cloning, Avatar Generation
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health & Status Endpoints
# ============================================================

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Newsletter Video Pipeline API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    """
    Check health of all pipeline services.

    Returns status of:
    - Voice Cloner (GPU Server)
    - Avatar Generator (GPU Server)
    - Video Processor (Local)
    - Social Publisher (Local)
    - Script Generator (Local)
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await orchestrator.health_check()


# ============================================================
# Pipeline Endpoints
# ============================================================

@app.post("/pipeline", response_model=PipelineResponse)
async def execute_pipeline(
    request: PipelineRequest,
    background_tasks: BackgroundTasks,
    async_mode: bool = False,
):
    """
    Execute the full newsletter-to-video pipeline.

    ## Steps:
    1. **Script Generation**: Convert newsletter to video script(s)
    2. **Voice Synthesis**: Generate audio using your cloned voice
    3. **Avatar Video**: Create video with lip-synced avatar
    4. **Video Processing**: Optimize for target platforms
    5. **Publishing** (optional): Upload to social media

    ## Parameters:
    - `async_mode`: If true, returns immediately with job_id for polling

    ## Example Request:
    ```json
    {
        "newsletter_content": "Your newsletter text here...",
        "newsletter_title": "Weekly Update #42",
        "generate_long_form": true,
        "generate_shorts": true,
        "shorts_count": 3,
        "target_platforms": ["youtube", "tiktok", "instagram"],
        "auto_publish": false
    }
    ```
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if async_mode:
        # Run in background and return job ID
        job_response = PipelineResponse(
            job_id="pending",
            status="pending",
            progress_percent=0,
            message="Job queued for processing",
        )

        async def run_pipeline():
            await orchestrator.execute_pipeline(request)

        background_tasks.add_task(run_pipeline)

        # Get actual job ID (created when pipeline starts)
        # For now, return a placeholder
        return PipelineResponse(
            job_id="queued",
            status="pending",
            progress_percent=0,
        )

    # Synchronous execution
    try:
        result = await orchestrator.execute_pipeline(request)
        return result
    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")


@app.get("/pipeline/{job_id}", response_model=PipelineResponse)
async def get_pipeline_status(job_id: str):
    """
    Get status and results of a pipeline job.

    Returns current progress, completed stages, and outputs.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    job = await orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@app.get("/pipeline", response_model=list[PipelineResponse])
async def list_pipeline_jobs(limit: int = 50):
    """List recent pipeline jobs."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return await orchestrator.list_jobs(limit)


# ============================================================
# Quick Action Endpoints
# ============================================================

@app.post("/quick/script")
async def quick_generate_script(
    content: str,
    title: str = "Newsletter",
    tone: str = "professional",
):
    """
    Quickly generate just a script from newsletter content.

    Use this for testing or when you only need the script.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{orchestrator.script_generator_url}/generate/quick",
            params={
                "content": content,
                "title": title,
                "tone": tone,
            },
        )
        return response.json()


@app.post("/quick/voice-test")
async def quick_voice_test(
    text: str = "Hello, this is a test of the voice cloning system.",
    voice_id: Optional[str] = None,
):
    """
    Test voice synthesis with a short text.

    Returns audio URL for playback.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{orchestrator.voice_service_url}/synthesize",
            json={
                "text": text,
                "voice_id": voice_id,
            },
        )
        return response.json()


@app.post("/quick/avatar-test")
async def quick_avatar_test(
    audio_path: str,
    avatar_id: Optional[str] = None,
):
    """
    Test avatar video generation with an audio file.

    Returns video URL.
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{orchestrator.avatar_service_url}/generate",
            json={
                "audio_path": audio_path,
                "avatar_id": avatar_id,
            },
        )
        return response.json()


# ============================================================
# Configuration Endpoints
# ============================================================

@app.get("/voices")
async def list_voices():
    """List available cloned voices."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{orchestrator.voice_service_url}/voices")
        return response.json()


@app.get("/avatars")
async def list_avatars():
    """List available avatars."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{orchestrator.avatar_service_url}/avatars")
        return response.json()


@app.get("/platforms")
async def list_platforms():
    """List available publishing platforms and their connection status."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{orchestrator.social_publisher_url}/platforms")
        return response.json()


def main():
    """Run the API Gateway."""
    uvicorn.run(
        "services.api_gateway.app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true",
        workers=int(os.getenv("API_WORKERS", "1")),
    )


if __name__ == "__main__":
    main()
