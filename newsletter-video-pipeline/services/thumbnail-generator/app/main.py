"""
Newsletter Video Pipeline - AI Thumbnail Generator.

Generates eye-catching thumbnails using:
- AI-powered layout and composition
- Dynamic text with proven engagement patterns
- Face detection and enhancement
- A/B testing variants
- Brand kit integration
"""

import asyncio
import io
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services."""
    logger.info("Thumbnail Generator Service starting...")
    yield
    logger.info("Thumbnail Generator Service stopped")


app = FastAPI(
    title="Thumbnail Generator Service",
    description="AI-powered video thumbnail generation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - restrict in production
# Set CORS_ORIGINS env var to comma-separated list of allowed origins
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ============================================================
# Models
# ============================================================

class ThumbnailStyle(BaseModel):
    """Thumbnail style configuration."""
    template: str = "modern"  # modern, minimal, bold, youtube, tiktok
    color_scheme: str = "auto"  # auto, brand, custom
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None


class TextElement(BaseModel):
    """Text element for thumbnail."""
    text: str
    position: str = "center"  # top, center, bottom, left, right
    font_size: str = "large"  # small, medium, large, xlarge
    font_weight: str = "bold"
    color: str = "#FFFFFF"
    outline: bool = True
    outline_color: str = "#000000"
    shadow: bool = True


class ThumbnailRequest(BaseModel):
    """Thumbnail generation request."""
    title: str
    subtitle: Optional[str] = None
    style: ThumbnailStyle = ThumbnailStyle()
    text_elements: Optional[List[TextElement]] = None
    include_face: bool = True
    face_position: str = "right"  # left, right, center
    background_type: str = "gradient"  # solid, gradient, image, blur
    background_image_url: Optional[str] = None
    emoji: Optional[str] = None
    emoji_position: str = "top-right"
    dimensions: str = "youtube"  # youtube (1280x720), tiktok (1080x1920), instagram (1080x1080)
    brand_kit_id: Optional[str] = None


class ThumbnailVariant(BaseModel):
    """A/B test variant of thumbnail."""
    id: str
    url: str
    preview_url: str
    style_description: str
    text_variation: str


class ThumbnailResponse(BaseModel):
    """Thumbnail generation response."""
    id: str
    url: str
    preview_url: str
    dimensions: dict
    variants: Optional[List[ThumbnailVariant]] = None
    created_at: datetime


class ThumbnailTemplate(BaseModel):
    """Thumbnail template."""
    id: str
    name: str
    description: str
    preview_url: str
    category: str  # youtube, tiktok, instagram, general
    style: ThumbnailStyle
    elements: List[dict]


# ============================================================
# File Upload Validation
# ============================================================

# Maximum file sizes
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB

# Allowed MIME types
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp"
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"
}

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}


async def validate_image_upload(file: UploadFile) -> bytes:
    """Validate and read an uploaded image file."""
    # Check content type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type: {file.content_type}. Allowed: {ALLOWED_IMAGE_TYPES}"
        )

    # Check extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image extension: {ext}. Allowed: {ALLOWED_IMAGE_EXTENSIONS}"
            )

    # Read and check size
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size: {MAX_IMAGE_SIZE // (1024*1024)} MB"
        )

    # Basic magic number validation
    if not _is_valid_image(content):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid image"
        )

    return content


async def validate_video_upload(file: UploadFile) -> bytes:
    """Validate and read an uploaded video file."""
    # Check content type
    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid video type: {file.content_type}. Allowed: {ALLOWED_VIDEO_TYPES}"
        )

    # Check extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid video extension: {ext}. Allowed: {ALLOWED_VIDEO_EXTENSIONS}"
            )

    # Read and check size
    content = await file.read()
    if len(content) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Video too large. Maximum size: {MAX_VIDEO_SIZE // (1024*1024)} MB"
        )

    return content


def _is_valid_image(content: bytes) -> bool:
    """Check if content appears to be a valid image using magic numbers."""
    if len(content) < 8:
        return False

    # JPEG
    if content[:2] == b'\xff\xd8':
        return True
    # PNG
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    # GIF
    if content[:6] in (b'GIF87a', b'GIF89a'):
        return True
    # WebP
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return True

    return False


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    if not filename:
        return "upload"
    # Remove path separators and get just the filename
    name = Path(filename).name
    # Remove any dangerous characters
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name or "upload"


# ============================================================
# Generation Endpoints
# ============================================================

@app.post("/generate", response_model=ThumbnailResponse)
async def generate_thumbnail(request: ThumbnailRequest):
    """
    Generate a thumbnail from text and optional image.
    Uses AI to create engaging compositions.
    """
    thumbnail_id = str(uuid.uuid4())

    # Get dimensions
    dims = _get_dimensions(request.dimensions)

    # Generate thumbnail
    output_path = await _generate_thumbnail(
        thumbnail_id=thumbnail_id,
        request=request,
        width=dims["width"],
        height=dims["height"],
    )

    return ThumbnailResponse(
        id=thumbnail_id,
        url=f"/thumbnails/{thumbnail_id}.png",
        preview_url=f"/thumbnails/{thumbnail_id}_preview.png",
        dimensions=dims,
        created_at=datetime.utcnow(),
    )


@app.post("/generate-variants", response_model=ThumbnailResponse)
async def generate_thumbnail_variants(
    request: ThumbnailRequest,
    variant_count: int = Query(3, ge=2, le=5),
):
    """
    Generate multiple thumbnail variants for A/B testing.
    Each variant has different text, colors, or layout.
    """
    thumbnail_id = str(uuid.uuid4())
    dims = _get_dimensions(request.dimensions)

    variants = []

    # Generate main thumbnail
    main_path = await _generate_thumbnail(
        thumbnail_id=thumbnail_id,
        request=request,
        width=dims["width"],
        height=dims["height"],
    )

    # Generate variants with different styles
    variant_styles = [
        {"style": "bold", "text_variation": "Question hook"},
        {"style": "minimal", "text_variation": "Short & punchy"},
        {"style": "emotional", "text_variation": "Curiosity gap"},
        {"style": "data", "text_variation": "Number-focused"},
    ]

    for i, var_style in enumerate(variant_styles[:variant_count - 1]):
        var_id = f"{thumbnail_id}_v{i + 1}"

        # Modify request for variant
        var_request = request.copy()
        var_request.style.template = var_style["style"]

        # Generate variant
        var_path = await _generate_thumbnail(
            thumbnail_id=var_id,
            request=var_request,
            width=dims["width"],
            height=dims["height"],
        )

        variants.append(ThumbnailVariant(
            id=var_id,
            url=f"/thumbnails/{var_id}.png",
            preview_url=f"/thumbnails/{var_id}_preview.png",
            style_description=var_style["style"],
            text_variation=var_style["text_variation"],
        ))

    return ThumbnailResponse(
        id=thumbnail_id,
        url=f"/thumbnails/{thumbnail_id}.png",
        preview_url=f"/thumbnails/{thumbnail_id}_preview.png",
        dimensions=dims,
        variants=variants,
        created_at=datetime.utcnow(),
    )


@app.post("/generate-from-video")
async def generate_from_video(
    video_file: UploadFile = File(...),
    title: str = Form(...),
    timestamp: float = Form(None, description="Specific timestamp to extract frame"),
    auto_select_best: bool = Form(True),
):
    """
    Generate thumbnail from video file.
    Can auto-select the best frame or use a specific timestamp.
    """
    # Validate video upload
    content = await validate_video_upload(video_file)

    thumbnail_id = str(uuid.uuid4())

    # Save uploaded video temporarily
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/thumbnails"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use sanitized filename extension
    safe_ext = Path(_sanitize_filename(video_file.filename or "video.mp4")).suffix or ".mp4"
    video_path = output_dir / f"{thumbnail_id}_video{safe_ext}"

    with open(video_path, "wb") as f:
        f.write(content)

    try:
        # Extract best frame
        if auto_select_best:
            frame_path = await _extract_best_frame(video_path, output_dir, thumbnail_id)
        else:
            frame_path = await _extract_frame_at_timestamp(
                video_path, output_dir, thumbnail_id, timestamp or 0
            )

        # Generate thumbnail with text overlay
        request = ThumbnailRequest(
            title=title,
            background_type="image",
            background_image_url=str(frame_path),
        )

        output_path = await _generate_thumbnail(
            thumbnail_id=thumbnail_id,
            request=request,
            width=1280,
            height=720,
        )

        return ThumbnailResponse(
            id=thumbnail_id,
            url=f"/thumbnails/{thumbnail_id}.png",
            preview_url=f"/thumbnails/{thumbnail_id}_preview.png",
            dimensions={"width": 1280, "height": 720},
            created_at=datetime.utcnow(),
        )

    finally:
        # Cleanup video file
        if video_path.exists():
            video_path.unlink()


@app.post("/generate-from-face")
async def generate_with_face(
    face_image: UploadFile = File(...),
    title: str = Form(...),
    expression: str = Form("surprised", description="surprised, happy, serious, excited"),
    style: str = Form("youtube"),
):
    """
    Generate thumbnail featuring a face image.
    Applies enhancement and optimal positioning.
    """
    # Validate image upload
    content = await validate_image_upload(face_image)

    thumbnail_id = str(uuid.uuid4())

    # Save uploaded image
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/thumbnails"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use sanitized filename extension
    safe_ext = Path(_sanitize_filename(face_image.filename or "face.png")).suffix or ".png"
    face_path = output_dir / f"{thumbnail_id}_face{safe_ext}"

    with open(face_path, "wb") as f:
        f.write(content)

    try:
        # Enhance face
        enhanced_path = await _enhance_face(face_path, expression)

        # Generate thumbnail
        request = ThumbnailRequest(
            title=title,
            include_face=True,
            face_position="right",
            style=ThumbnailStyle(template=style),
        )

        output_path = await _generate_thumbnail_with_face(
            thumbnail_id=thumbnail_id,
            request=request,
            face_path=enhanced_path,
            width=1280,
            height=720,
        )

        return ThumbnailResponse(
            id=thumbnail_id,
            url=f"/thumbnails/{thumbnail_id}.png",
            preview_url=f"/thumbnails/{thumbnail_id}_preview.png",
            dimensions={"width": 1280, "height": 720},
            created_at=datetime.utcnow(),
        )

    finally:
        if face_path.exists():
            face_path.unlink()


# ============================================================
# Template Endpoints
# ============================================================

@app.get("/templates", response_model=List[ThumbnailTemplate])
async def list_templates(
    category: Optional[str] = None,
):
    """List available thumbnail templates."""
    templates = [
        ThumbnailTemplate(
            id="modern_youtube",
            name="Modern YouTube",
            description="Clean, bold text with gradient background",
            preview_url="/templates/modern_youtube.png",
            category="youtube",
            style=ThumbnailStyle(template="modern"),
            elements=[],
        ),
        ThumbnailTemplate(
            id="viral_tiktok",
            name="Viral TikTok",
            description="Eye-catching vertical format",
            preview_url="/templates/viral_tiktok.png",
            category="tiktok",
            style=ThumbnailStyle(template="bold"),
            elements=[],
        ),
        ThumbnailTemplate(
            id="minimal_pro",
            name="Minimal Pro",
            description="Professional, minimalist design",
            preview_url="/templates/minimal_pro.png",
            category="general",
            style=ThumbnailStyle(template="minimal"),
            elements=[],
        ),
    ]

    if category:
        templates = [t for t in templates if t.category == category]

    return templates


@app.post("/templates/{template_id}/apply")
async def apply_template(
    template_id: str,
    title: str,
    subtitle: Optional[str] = None,
    background_image: Optional[UploadFile] = File(None),
):
    """Apply a template to generate a thumbnail."""
    # TODO: Load template and apply
    return await generate_thumbnail(
        ThumbnailRequest(
            title=title,
            subtitle=subtitle,
            style=ThumbnailStyle(template="modern"),
        )
    )


# ============================================================
# Security Utilities
# ============================================================

import re

# Valid thumbnail ID pattern: UUID or UUID with variant suffix
_VALID_THUMBNAIL_ID = re.compile(r'^[a-f0-9\-]{8,}(_v\d+)?$', re.IGNORECASE)


def _sanitize_thumbnail_id(thumbnail_id: str) -> str:
    """
    Sanitize thumbnail ID to prevent path traversal attacks.

    Valid IDs are UUIDs optionally followed by _v1, _v2, etc. for variants.
    """
    # Strip any path separators or parent directory references
    sanitized = thumbnail_id.replace("/", "").replace("\\", "").replace("..", "")

    # Validate format
    if not _VALID_THUMBNAIL_ID.match(sanitized):
        raise HTTPException(
            status_code=400,
            detail="Invalid thumbnail ID format"
        )

    return sanitized


def _get_safe_file_path(output_dir: Path, thumbnail_id: str, suffix: str = ".png") -> Path:
    """
    Get a safe file path, ensuring it stays within the output directory.
    """
    sanitized_id = _sanitize_thumbnail_id(thumbnail_id)
    file_path = (output_dir / f"{sanitized_id}{suffix}").resolve()

    # Ensure the resolved path is within the output directory
    output_dir_resolved = output_dir.resolve()
    if not str(file_path).startswith(str(output_dir_resolved)):
        raise HTTPException(
            status_code=400,
            detail="Invalid thumbnail path"
        )

    return file_path


# ============================================================
# Download Endpoints
# ============================================================

@app.get("/thumbnails/{thumbnail_id}.png")
async def download_thumbnail(thumbnail_id: str):
    """Download generated thumbnail."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/thumbnails"))
    file_path = _get_safe_file_path(output_dir, thumbnail_id, ".png")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(file_path, media_type="image/png")


@app.get("/thumbnails/{thumbnail_id}_preview.png")
async def download_thumbnail_preview(thumbnail_id: str):
    """Download thumbnail preview (lower resolution)."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/thumbnails"))
    file_path = _get_safe_file_path(output_dir, thumbnail_id, "_preview.png")

    if not file_path.exists():
        # Fall back to main thumbnail
        file_path = _get_safe_file_path(output_dir, thumbnail_id, ".png")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(file_path, media_type="image/png")


# ============================================================
# Helper Functions
# ============================================================

def _get_dimensions(dimension_type: str) -> dict:
    """Get pixel dimensions for thumbnail type."""
    dimensions = {
        "youtube": {"width": 1280, "height": 720},
        "youtube_large": {"width": 1920, "height": 1080},
        "tiktok": {"width": 1080, "height": 1920},
        "instagram": {"width": 1080, "height": 1080},
        "instagram_story": {"width": 1080, "height": 1920},
        "twitter": {"width": 1200, "height": 675},
    }
    return dimensions.get(dimension_type, dimensions["youtube"])


async def _generate_thumbnail(
    thumbnail_id: str,
    request: ThumbnailRequest,
    width: int,
    height: int,
) -> Path:
    """Generate thumbnail image."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PIL not installed. Run: pip install Pillow"
        )

    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/thumbnails"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create base image
    if request.background_type == "gradient":
        img = _create_gradient_background(width, height, request.style)
    elif request.background_type == "solid":
        color = request.style.primary_color or "#1a1a2e"
        img = Image.new("RGB", (width, height), color)
    else:
        img = Image.new("RGB", (width, height), "#1a1a2e")

    draw = ImageDraw.Draw(img)

    # Add text
    try:
        # Try to load a nice font, fall back to default
        font_size = int(height * 0.12)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(font_size * 0.6))
    except:
        font = ImageFont.load_default()
        small_font = font

    # Draw title with outline
    title = request.title.upper()

    # Calculate text position
    bbox = draw.textbbox((0, 0), title, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (width - text_width) // 2
    y = (height - text_height) // 2

    # Draw outline
    outline_color = "#000000"
    for dx in [-3, 0, 3]:
        for dy in [-3, 0, 3]:
            draw.text((x + dx, y + dy), title, font=font, fill=outline_color)

    # Draw main text
    draw.text((x, y), title, font=font, fill="#FFFFFF")

    # Add subtitle if present
    if request.subtitle:
        subtitle_bbox = draw.textbbox((0, 0), request.subtitle, font=small_font)
        sub_width = subtitle_bbox[2] - subtitle_bbox[0]
        sub_x = (width - sub_width) // 2
        sub_y = y + text_height + 20
        draw.text((sub_x, sub_y), request.subtitle, font=small_font, fill="#FFD700")

    # Add emoji if present
    if request.emoji:
        emoji_size = int(height * 0.15)
        emoji_pos = _get_emoji_position(request.emoji_position, width, height, emoji_size)
        # Note: Would need emoji font support for actual emojis

    # Save
    output_path = output_dir / f"{thumbnail_id}.png"
    img.save(output_path, "PNG", quality=95)

    # Create preview
    preview = img.resize((width // 2, height // 2), Image.LANCZOS)
    preview_path = output_dir / f"{thumbnail_id}_preview.png"
    preview.save(preview_path, "PNG")

    return output_path


def _create_gradient_background(width: int, height: int, style: ThumbnailStyle) -> "Image":
    """Create gradient background image."""
    from PIL import Image

    # Default gradient colors based on style
    gradients = {
        "modern": ("#1a1a2e", "#16213e", "#0f3460"),
        "bold": ("#ff0000", "#ff6b6b", "#ffd93d"),
        "minimal": ("#2c3e50", "#3498db", "#2980b9"),
        "youtube": ("#ff0000", "#cc0000", "#990000"),
        "tiktok": ("#000000", "#25f4ee", "#fe2c55"),
    }

    colors = gradients.get(style.template, gradients["modern"])

    img = Image.new("RGB", (width, height))

    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            # Top to middle gradient
            r = int(int(colors[0][1:3], 16) * (1 - ratio * 2) + int(colors[1][1:3], 16) * ratio * 2)
            g = int(int(colors[0][3:5], 16) * (1 - ratio * 2) + int(colors[1][3:5], 16) * ratio * 2)
            b = int(int(colors[0][5:7], 16) * (1 - ratio * 2) + int(colors[1][5:7], 16) * ratio * 2)
        else:
            # Middle to bottom gradient
            ratio2 = (ratio - 0.5) * 2
            r = int(int(colors[1][1:3], 16) * (1 - ratio2) + int(colors[2][1:3], 16) * ratio2)
            g = int(int(colors[1][3:5], 16) * (1 - ratio2) + int(colors[2][3:5], 16) * ratio2)
            b = int(int(colors[1][5:7], 16) * (1 - ratio2) + int(colors[2][5:7], 16) * ratio2)

        for x in range(width):
            img.putpixel((x, y), (r, g, b))

    return img


def _get_emoji_position(position: str, width: int, height: int, size: int) -> tuple:
    """Get pixel position for emoji."""
    positions = {
        "top-left": (20, 20),
        "top-right": (width - size - 20, 20),
        "bottom-left": (20, height - size - 20),
        "bottom-right": (width - size - 20, height - size - 20),
        "center": ((width - size) // 2, (height - size) // 2),
    }
    return positions.get(position, positions["top-right"])


async def _extract_best_frame(video_path: Path, output_dir: Path, thumbnail_id: str) -> Path:
    """Extract the best frame from video for thumbnail."""
    import subprocess

    # Extract multiple frames and pick the best one
    # For now, extract frame at 25% of video duration
    output_path = output_dir / f"{thumbnail_id}_frame.png"

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", "select='eq(pict_type,I)',scale=1920:1080",
        "-vframes", "1",
        "-y",
        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    return output_path


async def _extract_frame_at_timestamp(
    video_path: Path,
    output_dir: Path,
    thumbnail_id: str,
    timestamp: float,
) -> Path:
    """Extract frame at specific timestamp."""
    import subprocess

    output_path = output_dir / f"{thumbnail_id}_frame.png"

    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-y",
        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    return output_path


async def _enhance_face(face_path: Path, expression: str) -> Path:
    """Enhance face image for thumbnail."""
    # TODO: Implement face enhancement
    # For now, return original
    return face_path


async def _generate_thumbnail_with_face(
    thumbnail_id: str,
    request: ThumbnailRequest,
    face_path: Path,
    width: int,
    height: int,
) -> Path:
    """Generate thumbnail with face overlay."""
    # TODO: Implement face composition
    return await _generate_thumbnail(thumbnail_id, request, width, height)


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "thumbnail-generator",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5014)
