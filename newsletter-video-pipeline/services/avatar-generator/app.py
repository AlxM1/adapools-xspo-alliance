"""
FastAPI application for Avatar Generator Service.

This runs on the Windows GPU server and exposes REST API for:
- Avatar creation from video
- Video generation with lip-sync
- Avatar management
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from .service import AvatarGeneratorService
from .models import (
    CreateAvatarRequest,
    CreateAvatarResponse,
    GenerateVideoRequest,
    GenerateVideoResponse,
    AvatarModel,
    AvatarListResponse,
    AvatarDeleteResponse,
    HealthResponse,
    OutputResolution,
    AspectRatio,
)

# Global service instance
avatar_service: Optional[AvatarGeneratorService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global avatar_service

    # Startup
    logger.info("Starting Avatar Generator Service...")

    avatar_service = AvatarGeneratorService(
        musetalk_path=os.getenv("AVATAR_MUSETALK_PATH", "/models/musetalk"),
        liveportrait_path=os.getenv("AVATAR_LIVEPORTRAIT_PATH", "/models/liveportrait"),
        avatars_dir=os.getenv("AVATAR_AVATARS_DIR", "/data/avatars"),
        temp_dir=os.getenv("AVATAR_TEMP_DIR", "/tmp/avatar_generator"),
        device=os.getenv("AVATAR_DEVICE", "cuda"),
    )

    await avatar_service.initialize()
    logger.info("Avatar Generator Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Avatar Generator Service...")
    if avatar_service:
        await avatar_service.cleanup()
    logger.info("Avatar Generator Service stopped")


app = FastAPI(
    title="Avatar Generator Service",
    description="MuseTalk + LivePortrait based avatar video generation service",
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
    """Check service health and GPU status."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await avatar_service.health_check()


@app.get("/avatars", response_model=AvatarListResponse)
async def list_avatars():
    """List all available avatars."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await avatar_service.list_avatars()


@app.get("/avatars/{avatar_id}", response_model=AvatarModel)
async def get_avatar(avatar_id: str):
    """Get a specific avatar by ID."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    avatar = await avatar_service.get_avatar(avatar_id)
    if not avatar:
        raise HTTPException(status_code=404, detail=f"Avatar not found: {avatar_id}")
    return avatar


@app.post("/avatars/create", response_model=CreateAvatarResponse)
async def create_avatar(
    name: str = Form(..., description="Name for the avatar"),
    description: Optional[str] = Form(None, description="Avatar description"),
    set_as_default: bool = Form(default=False),
    remove_background: bool = Form(default=False),
    extract_body: bool = Form(default=False),
    video_file: UploadFile = File(..., description="Reference video file"),
):
    """
    Create an avatar from a reference video.

    Upload a video (MP4, MOV, AVI) of yourself speaking.
    For best results, use a video of 10-30 seconds with a clear face view.
    """
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

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
        request = CreateAvatarRequest(
            name=name,
            description=description,
            set_as_default=set_as_default,
            remove_background=remove_background,
            extract_body=extract_body,
        )

        # Create avatar
        result = await avatar_service.create_avatar(video_path, request)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to create avatar: {e}")
        raise HTTPException(status_code=500, detail=f"Avatar creation failed: {e}")
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.delete("/avatars/{avatar_id}", response_model=AvatarDeleteResponse)
async def delete_avatar(avatar_id: str):
    """Delete an avatar."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await avatar_service.delete_avatar(avatar_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result


@app.post("/avatars/{avatar_id}/set-default")
async def set_default_avatar(avatar_id: str):
    """Set an avatar as the default."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    success = await avatar_service.set_default_avatar(avatar_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Avatar not found: {avatar_id}")
    return {"message": f"Avatar {avatar_id} set as default", "success": True}


@app.post("/generate", response_model=GenerateVideoResponse)
async def generate_video(request: GenerateVideoRequest):
    """
    Generate a video with the avatar speaking the provided audio.

    The audio file must already exist on the server (e.g., from voice synthesis).
    """
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await avatar_service.generate_video(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Video generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {e}")


@app.post("/generate/with-audio", response_model=GenerateVideoResponse)
async def generate_video_with_audio(
    avatar_id: Optional[str] = Form(None),
    resolution: OutputResolution = Form(default=OutputResolution.FHD),
    aspect_ratio: AspectRatio = Form(default=AspectRatio.LANDSCAPE),
    fps: int = Form(default=30),
    enhance_face: bool = Form(default=True),
    use_liveportrait: bool = Form(default=True),
    audio_file: UploadFile = File(..., description="Audio file for lip-sync"),
):
    """
    Generate a video with uploaded audio file.

    Upload an audio file (WAV, MP3) and generate a video with lip-sync.
    """
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Validate audio file
    ext = Path(audio_file.filename or "").suffix.lower()
    if ext not in [".wav", ".mp3", ".ogg", ".m4a", ".flac"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audio type: {ext}. Supported: wav, mp3, ogg, m4a, flac"
        )

    # Save uploaded file
    temp_dir = Path(tempfile.mkdtemp())
    audio_path = temp_dir / f"audio{ext}"

    try:
        with open(audio_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)

        # Create request
        request = GenerateVideoRequest(
            avatar_id=avatar_id,
            audio_path=str(audio_path),
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            fps=fps,
            enhance_face=enhance_face,
            use_liveportrait=use_liveportrait,
        )

        # Generate video
        result = await avatar_service.generate_video(request)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Video generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {e}")
    finally:
        # Cleanup temp audio after processing
        # Note: Keep for a bit in case of retry
        pass


@app.get("/video/{filename}")
async def get_video(filename: str, background_tasks: BackgroundTasks):
    """Download a generated video file."""
    if not avatar_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    file_path = avatar_service.temp_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    # Schedule cleanup after download (keep for 2 hours)
    def cleanup_later():
        import time
        time.sleep(7200)
        if file_path.exists():
            file_path.unlink()

    background_tasks.add_task(cleanup_later)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=filename,
    )


def main():
    """Run the avatar generator service."""
    uvicorn.run(
        "services.avatar_generator.app:app",
        host=os.getenv("AVATAR_HOST", "0.0.0.0"),
        port=int(os.getenv("AVATAR_PORT", "5003")),
        reload=os.getenv("AVATAR_RELOAD", "false").lower() == "true",
        workers=1,  # Single worker for GPU model
    )


if __name__ == "__main__":
    main()
