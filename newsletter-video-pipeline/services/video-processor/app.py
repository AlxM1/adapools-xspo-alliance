"""
FastAPI application for Video Processor Service.

This runs on the Linux VM and exposes REST API for:
- Video format conversion
- Multi-platform optimization
- Shorts generation
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from .service import VideoProcessorService
from .models import (
    ProcessVideoRequest,
    ProcessVideoResponse,
    VideoInfoResponse,
    HealthResponse,
    Platform,
    VideoFormat,
)

# Global service instance
video_service: Optional[VideoProcessorService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global video_service

    # Startup
    logger.info("Starting Video Processor Service...")

    video_service = VideoProcessorService(
        ffmpeg_path=os.getenv("VIDEO_FFMPEG_PATH", "ffmpeg"),
        output_dir=os.getenv("VIDEO_OUTPUT_DIR", "/data/videos/output"),
        temp_dir=os.getenv("VIDEO_TEMP_DIR", "/tmp/video_processor"),
    )

    await video_service.initialize()
    logger.info("Video Processor Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Video Processor Service...")
    if video_service:
        await video_service.cleanup()
    logger.info("Video Processor Service stopped")


app = FastAPI(
    title="Video Processor Service",
    description="FFmpeg based video processing and multi-platform optimization",
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


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    if not video_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await video_service.health_check()


@app.post("/process", response_model=ProcessVideoResponse)
async def process_video(request: ProcessVideoRequest):
    """
    Process a video for specified platform(s).

    The input video must already exist on the server.
    """
    if not video_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await video_service.process_video(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Video processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")


@app.post("/process/upload", response_model=ProcessVideoResponse)
async def process_uploaded_video(
    platforms: str = "all",  # Comma-separated platform names
    output_format: VideoFormat = VideoFormat.MP4,
    add_captions: bool = False,
    normalize_audio: bool = True,
    generate_shorts: bool = False,
    shorts_count: int = 3,
    video_file: UploadFile = File(..., description="Video file to process"),
):
    """
    Upload and process a video for specified platform(s).
    """
    if not video_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Parse platforms
    platform_list = []
    for p in platforms.split(","):
        p = p.strip().lower()
        try:
            platform_list.append(Platform(p))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid platform: {p}")

    # Validate file type
    ext = Path(video_file.filename or "").suffix.lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {ext}. Supported: mp4, mov, avi, mkv, webm"
        )

    # Save uploaded file
    temp_dir = Path(tempfile.mkdtemp())
    video_path = temp_dir / f"upload{ext}"

    try:
        with open(video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)

        # Create request
        request = ProcessVideoRequest(
            input_path=str(video_path),
            platforms=platform_list,
            output_format=output_format,
            add_captions=add_captions,
            normalize_audio=normalize_audio,
            generate_shorts=generate_shorts,
            shorts_count=shorts_count,
        )

        # Process
        result = await video_service.process_video(request)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Video processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
    finally:
        # Cleanup uploaded file (keep processed outputs)
        if video_path.exists():
            video_path.unlink()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/info")
async def get_video_info(video_path: str) -> VideoInfoResponse:
    """Get information about a video file."""
    if not video_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        return await video_service.get_video_info(video_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/video/{filename}")
async def download_video(filename: str, background_tasks: BackgroundTasks):
    """Download a processed video file."""
    if not video_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Check in temp dir
    file_path = video_service.temp_dir / filename
    if not file_path.exists():
        # Check in output dir
        file_path = video_service.output_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=filename,
    )


@app.get("/platforms")
async def list_platforms():
    """List available platforms and their specifications."""
    return {
        "platforms": [
            {
                "id": p.value,
                "name": p.name,
                "specs": VideoProcessorService.PLATFORM_SPECS.get(p, {}),
            }
            for p in Platform
            if p != Platform.ALL
        ]
    }


def main():
    """Run the video processor service."""
    uvicorn.run(
        "services.video_processor.app:app",
        host=os.getenv("VIDEO_HOST", "0.0.0.0"),
        port=int(os.getenv("VIDEO_PORT", "5005")),
        reload=os.getenv("VIDEO_RELOAD", "false").lower() == "true",
        workers=int(os.getenv("VIDEO_WORKERS", "2")),
    )


if __name__ == "__main__":
    main()
