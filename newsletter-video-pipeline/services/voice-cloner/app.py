"""
FastAPI application for Voice Cloner Service.

This runs on the Windows GPU server and exposes REST API for:
- Voice cloning from audio samples
- Text-to-speech synthesis
- Voice management
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

from .service import VoiceClonerService
from .models import (
    VoiceCloneRequest,
    VoiceCloneResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    VoiceModel,
    VoiceListResponse,
    VoiceDeleteResponse,
    HealthResponse,
    VoiceLanguage,
)

# Global service instance
voice_service: Optional[VoiceClonerService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global voice_service

    # Startup
    logger.info("Starting Voice Cloner Service...")

    voice_service = VoiceClonerService(
        model_name=os.getenv("VOICE_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2"),
        voices_dir=os.getenv("VOICE_VOICES_DIR", "/data/voices"),
        temp_dir=os.getenv("VOICE_TEMP_DIR", "/tmp/voice_cloner"),
        device=os.getenv("VOICE_DEVICE", "cuda"),
        use_deepspeed=os.getenv("VOICE_USE_DEEPSPEED", "true").lower() == "true",
    )

    await voice_service.initialize()
    logger.info("Voice Cloner Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Voice Cloner Service...")
    if voice_service:
        await voice_service.cleanup()
    logger.info("Voice Cloner Service stopped")


app = FastAPI(
    title="Voice Cloner Service",
    description="XTTS-v2 based voice cloning and synthesis service",
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
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await voice_service.health_check()


@app.get("/voices", response_model=VoiceListResponse)
async def list_voices():
    """List all available cloned voices."""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await voice_service.list_voices()


@app.get("/voices/{voice_id}", response_model=VoiceModel)
async def get_voice(voice_id: str):
    """Get a specific voice by ID."""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    voice = await voice_service.get_voice(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail=f"Voice not found: {voice_id}")
    return voice


@app.post("/voices/clone", response_model=VoiceCloneResponse)
async def clone_voice(
    name: str = Form(..., description="Name for the voice"),
    description: Optional[str] = Form(None, description="Voice description"),
    language: VoiceLanguage = Form(default=VoiceLanguage.ENGLISH),
    set_as_default: bool = Form(default=False),
    audio_files: list[UploadFile] = File(..., description="Audio samples for cloning"),
):
    """
    Clone a voice from audio samples.

    Upload one or more audio files (WAV, MP3, FLAC) to create a voice clone.
    For best results, provide at least 30 seconds of clear speech.
    """
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not audio_files:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    # Save uploaded files to temp directory
    temp_dir = Path(tempfile.mkdtemp())
    saved_files = []

    try:
        for i, upload_file in enumerate(audio_files):
            # Validate file type
            if not upload_file.content_type or not upload_file.content_type.startswith("audio/"):
                # Also check by extension
                ext = Path(upload_file.filename or "").suffix.lower()
                if ext not in [".wav", ".mp3", ".flac", ".ogg", ".m4a"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid file type: {upload_file.content_type}. "
                               f"Supported: wav, mp3, flac, ogg, m4a"
                    )

            # Save file
            file_path = temp_dir / f"upload_{i}{Path(upload_file.filename or '.wav').suffix}"
            with open(file_path, "wb") as f:
                content = await upload_file.read()
                f.write(content)
            saved_files.append(file_path)

        # Create clone request
        request = VoiceCloneRequest(
            name=name,
            description=description,
            language=language,
            set_as_default=set_as_default,
        )

        # Clone voice
        result = await voice_service.clone_voice(saved_files, request)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to clone voice: {e}")
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {e}")
    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.delete("/voices/{voice_id}", response_model=VoiceDeleteResponse)
async def delete_voice(voice_id: str):
    """Delete a cloned voice."""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await voice_service.delete_voice(voice_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result


@app.post("/voices/{voice_id}/set-default")
async def set_default_voice(voice_id: str):
    """Set a voice as the default."""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    success = await voice_service.set_default_voice(voice_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Voice not found: {voice_id}")
    return {"message": f"Voice {voice_id} set as default", "success": True}


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(request: SynthesizeRequest):
    """
    Synthesize speech from text.

    Returns audio file path and metadata. Use /audio/{filename} to download.
    """
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await voice_service.synthesize(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")


@app.post("/synthesize/stream")
async def synthesize_stream(request: SynthesizeRequest):
    """
    Stream synthesized speech.

    Returns chunked audio data as the synthesis progresses.
    """
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        async def audio_generator():
            async for chunk in voice_service.synthesize_stream(request):
                yield chunk

        return StreamingResponse(
            audio_generator(),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=synthesis.wav",
                "Transfer-Encoding": "chunked",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Streaming synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")


@app.get("/audio/{filename}")
async def get_audio(filename: str, background_tasks: BackgroundTasks):
    """Download a generated audio file."""
    if not voice_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    file_path = voice_service.temp_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    # Schedule cleanup after download (keep for 1 hour)
    def cleanup_later():
        import time
        time.sleep(3600)
        if file_path.exists():
            file_path.unlink()

    background_tasks.add_task(cleanup_later)

    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=filename,
    )


def main():
    """Run the voice cloner service."""
    uvicorn.run(
        "services.voice_cloner.app:app",
        host=os.getenv("VOICE_HOST", "0.0.0.0"),
        port=int(os.getenv("VOICE_PORT", "5002")),
        reload=os.getenv("VOICE_RELOAD", "false").lower() == "true",
        workers=1,  # Single worker for GPU model
    )


if __name__ == "__main__":
    main()
