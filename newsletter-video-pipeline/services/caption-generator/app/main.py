"""
Newsletter Video Pipeline - Dynamic Caption Generator.

Generates animated, word-by-word captions in multiple styles:
- Karaoke (word highlighting)
- Bounce (animated pop-in)
- Typewriter (character by character)
- Wave (wavy text animation)
- Glow (neon glow effect)
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn

from .transcriber import Transcriber
from .caption_renderer import CaptionRenderer, CaptionStyle
from .ass_generator import ASSGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
transcriber: Optional[Transcriber] = None
renderer: Optional[CaptionRenderer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    global transcriber, renderer

    logger.info("Initializing Caption Generator Service...")

    transcriber = Transcriber()
    renderer = CaptionRenderer()

    logger.info("Caption Generator Service ready")
    yield

    logger.info("Caption Generator Service stopped")


app = FastAPI(
    title="Caption Generator Service",
    description="Generate animated captions with word-level timing",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Models
# ============================================================

class CaptionStyleEnum(str, Enum):
    KARAOKE = "karaoke"
    BOUNCE = "bounce"
    TYPEWRITER = "typewriter"
    WAVE = "wave"
    GLOW = "glow"
    HIGHLIGHT = "highlight"
    MINIMAL = "minimal"


class CaptionConfig(BaseModel):
    """Caption generation configuration."""
    style: CaptionStyleEnum = CaptionStyleEnum.KARAOKE
    font_family: str = "Montserrat"
    font_size: int = Field(default=72, ge=24, le=200)
    font_weight: str = "bold"
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFD700"  # Highlight color
    outline_color: str = "#000000"
    outline_width: int = Field(default=3, ge=0, le=10)
    shadow_color: str = "#000000"
    shadow_offset: int = Field(default=2, ge=0, le=10)
    position: str = "bottom"  # top, center, bottom
    margin_bottom: int = Field(default=50, ge=0, le=500)
    max_words_per_line: int = Field(default=6, ge=2, le=15)
    animation_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    background_box: bool = False
    background_color: str = "#000000"
    background_opacity: float = Field(default=0.7, ge=0, le=1)


class TranscriptionWord(BaseModel):
    """Word with timing information."""
    word: str
    start: float  # Start time in seconds
    end: float  # End time in seconds
    confidence: float = 1.0


class TranscriptionResult(BaseModel):
    """Full transcription with word-level timing."""
    text: str
    words: list[TranscriptionWord]
    duration: float
    language: str = "en"


class CaptionRequest(BaseModel):
    """Caption generation request."""
    transcription: Optional[TranscriptionResult] = None
    text: Optional[str] = None  # If no transcription, generate from text
    duration: Optional[float] = None  # Required if text is provided
    config: CaptionConfig = CaptionConfig()
    output_format: str = "ass"  # ass, srt, vtt, json


class CaptionResponse(BaseModel):
    """Caption generation response."""
    id: str
    status: str
    output_path: Optional[str] = None
    preview_url: Optional[str] = None
    word_count: int
    duration: float
    style: str


# ============================================================
# Transcription Endpoints
# ============================================================

@app.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    language: str = Form("en"),
):
    """
    Transcribe audio file with word-level timestamps.
    Supports WAV, MP3, MP4, M4A, FLAC.
    """
    # Save uploaded file
    suffix = Path(audio_file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await audio_file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await transcriber.transcribe(tmp_path, language)
        return result
    finally:
        os.unlink(tmp_path)


@app.post("/transcribe/url", response_model=TranscriptionResult)
async def transcribe_from_url(
    url: str,
    language: str = "en",
):
    """Transcribe audio from URL."""
    result = await transcriber.transcribe_url(url, language)
    return result


# ============================================================
# Caption Generation Endpoints
# ============================================================

@app.post("/captions/generate", response_model=CaptionResponse)
async def generate_captions(request: CaptionRequest):
    """
    Generate animated captions from transcription or text.
    Returns caption file in specified format.
    """
    caption_id = str(uuid.uuid4())

    # Get or generate transcription
    if request.transcription:
        transcription = request.transcription
    elif request.text and request.duration:
        # Generate word timing from text
        transcription = await transcriber.generate_timing(
            request.text,
            request.duration
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either transcription or text+duration must be provided"
        )

    # Generate captions based on format
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/captions"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if request.output_format == "ass":
        generator = ASSGenerator(request.config)
        output_path = output_dir / f"{caption_id}.ass"
        await generator.generate(transcription, output_path)
    elif request.output_format == "srt":
        output_path = output_dir / f"{caption_id}.srt"
        await renderer.generate_srt(transcription, request.config, output_path)
    elif request.output_format == "vtt":
        output_path = output_dir / f"{caption_id}.vtt"
        await renderer.generate_vtt(transcription, request.config, output_path)
    elif request.output_format == "json":
        output_path = output_dir / f"{caption_id}.json"
        await renderer.generate_json(transcription, request.config, output_path)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {request.output_format}")

    return CaptionResponse(
        id=caption_id,
        status="completed",
        output_path=str(output_path),
        word_count=len(transcription.words),
        duration=transcription.duration,
        style=request.config.style.value,
    )


@app.post("/captions/burn")
async def burn_captions(
    video_file: UploadFile = File(...),
    caption_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Burn captions directly onto video file.
    Returns video with hardcoded captions.
    """
    job_id = str(uuid.uuid4())

    # Save uploaded files
    video_suffix = Path(video_file.filename).suffix
    caption_suffix = Path(caption_file.filename).suffix

    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/captions"))
    output_dir.mkdir(parents=True, exist_ok=True)

    video_path = output_dir / f"{job_id}_input{video_suffix}"
    caption_path = output_dir / f"{job_id}_captions{caption_suffix}"
    output_path = output_dir / f"{job_id}_output{video_suffix}"

    with open(video_path, "wb") as f:
        f.write(await video_file.read())

    with open(caption_path, "wb") as f:
        f.write(await caption_file.read())

    # Burn captions
    await renderer.burn_captions(video_path, caption_path, output_path)

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"captioned_{video_file.filename}",
    )


@app.get("/captions/{caption_id}/download")
async def download_captions(caption_id: str):
    """Download generated caption file."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/captions"))

    # Find the file with any extension
    for ext in [".ass", ".srt", ".vtt", ".json"]:
        path = output_dir / f"{caption_id}{ext}"
        if path.exists():
            return FileResponse(path, filename=f"captions{ext}")

    raise HTTPException(status_code=404, detail="Caption file not found")


# ============================================================
# Style Presets
# ============================================================

@app.get("/styles")
async def list_styles():
    """List available caption styles with previews."""
    styles = [
        {
            "id": "karaoke",
            "name": "Karaoke",
            "description": "Words highlight as they're spoken",
            "preview_gif": "/static/previews/karaoke.gif",
        },
        {
            "id": "bounce",
            "name": "Bounce",
            "description": "Words pop in with bounce animation",
            "preview_gif": "/static/previews/bounce.gif",
        },
        {
            "id": "typewriter",
            "name": "Typewriter",
            "description": "Text types character by character",
            "preview_gif": "/static/previews/typewriter.gif",
        },
        {
            "id": "wave",
            "name": "Wave",
            "description": "Wavy text animation effect",
            "preview_gif": "/static/previews/wave.gif",
        },
        {
            "id": "glow",
            "name": "Glow",
            "description": "Neon glow effect on words",
            "preview_gif": "/static/previews/glow.gif",
        },
        {
            "id": "highlight",
            "name": "Highlight",
            "description": "Background highlight behind current word",
            "preview_gif": "/static/previews/highlight.gif",
        },
        {
            "id": "minimal",
            "name": "Minimal",
            "description": "Clean, simple captions",
            "preview_gif": "/static/previews/minimal.gif",
        },
    ]
    return styles


@app.get("/fonts")
async def list_fonts():
    """List available fonts."""
    fonts = [
        "Montserrat",
        "Roboto",
        "Open Sans",
        "Poppins",
        "Inter",
        "Oswald",
        "Bebas Neue",
        "Anton",
        "Raleway",
        "Source Sans Pro",
    ]
    return fonts


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "caption-generator",
        "transcriber_ready": transcriber is not None,
        "renderer_ready": renderer is not None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5011)
