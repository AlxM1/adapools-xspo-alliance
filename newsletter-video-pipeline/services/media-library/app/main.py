"""
Newsletter Video Pipeline - Media Library Service.

Provides:
- B-roll footage from Pexels, Pixabay, and local library
- Background music with mood detection
- Sound effects
- Brand assets management
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services."""
    logger.info("Media Library Service starting...")
    yield
    logger.info("Media Library Service stopped")


app = FastAPI(
    title="Media Library Service",
    description="B-roll, music, and asset management",
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

# API Keys
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")


# ============================================================
# Models
# ============================================================

class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"


class MoodCategory(str, Enum):
    UPBEAT = "upbeat"
    CALM = "calm"
    DRAMATIC = "dramatic"
    INSPIRING = "inspiring"
    DARK = "dark"
    HAPPY = "happy"
    SAD = "sad"
    CORPORATE = "corporate"
    ENERGETIC = "energetic"
    AMBIENT = "ambient"


class BRollResult(BaseModel):
    """B-roll search result."""
    id: str
    source: str  # pexels, pixabay, local
    url: str
    preview_url: str
    thumbnail_url: str
    duration: Optional[float] = None
    width: int
    height: int
    keywords: List[str]
    attribution: Optional[str] = None


class MusicTrack(BaseModel):
    """Background music track."""
    id: str
    title: str
    artist: str
    duration: float
    mood: MoodCategory
    bpm: Optional[int] = None
    source: str  # local, freepd, etc.
    url: str
    preview_url: str
    license: str


class SoundEffect(BaseModel):
    """Sound effect."""
    id: str
    name: str
    category: str
    duration: float
    url: str
    keywords: List[str]


class BrandAsset(BaseModel):
    """Brand asset (logo, intro, outro, etc.)."""
    id: str
    name: str
    asset_type: str  # logo, intro, outro, watermark, lower_third
    file_path: str
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    created_at: datetime


# ============================================================
# B-Roll Endpoints
# ============================================================

@app.get("/broll/search", response_model=List[BRollResult])
async def search_broll(
    query: str = Query(..., description="Search keywords"),
    orientation: str = Query("landscape", description="landscape, portrait, or square"),
    min_duration: int = Query(5, description="Minimum duration in seconds"),
    max_duration: int = Query(30, description="Maximum duration in seconds"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Search for B-roll footage from multiple sources.
    Automatically searches Pexels, Pixabay, and local library.
    """
    results = []

    # Search multiple sources in parallel
    tasks = []

    if PEXELS_API_KEY:
        tasks.append(_search_pexels(query, orientation, min_duration, max_duration, limit))

    if PIXABAY_API_KEY:
        tasks.append(_search_pixabay(query, orientation, min_duration, max_duration, limit))

    tasks.append(_search_local_broll(query, orientation, min_duration, max_duration, limit))

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in all_results:
        if isinstance(result, list):
            results.extend(result)

    # Sort by relevance and return
    return results[:limit]


@app.get("/broll/keywords")
async def extract_keywords(text: str):
    """
    Extract relevant B-roll keywords from text.
    Uses NLP to identify visual concepts.
    """
    keywords = await _extract_visual_keywords(text)
    return {"keywords": keywords}


@app.post("/broll/auto-select")
async def auto_select_broll(
    script: str,
    duration: float,
    style: str = "professional",
):
    """
    Automatically select and sequence B-roll for a script.
    Returns a timeline of B-roll clips matched to script sections.
    """
    # Extract keywords from script sections
    sections = _split_script_sections(script)

    timeline = []
    current_time = 0.0
    section_duration = duration / len(sections) if sections else duration

    for section in sections:
        keywords = await _extract_visual_keywords(section["text"])

        # Search for matching B-roll
        results = await search_broll(
            query=" ".join(keywords[:3]),
            min_duration=3,
            max_duration=15,
            limit=5,
        )

        if results:
            # Select best match
            clip = results[0]

            timeline.append({
                "start_time": current_time,
                "end_time": current_time + min(clip.duration or 5, section_duration),
                "clip": clip,
                "section_text": section["text"][:100],
                "keywords": keywords,
            })

        current_time += section_duration

    return {"timeline": timeline, "total_duration": duration}


# ============================================================
# Background Music Endpoints
# ============================================================

@app.get("/music/search", response_model=List[MusicTrack])
async def search_music(
    mood: Optional[MoodCategory] = None,
    min_duration: int = Query(60, description="Minimum duration in seconds"),
    max_duration: int = Query(300, description="Maximum duration in seconds"),
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    limit: int = Query(20, ge=1, le=50),
):
    """Search for background music tracks."""
    tracks = await _search_music_library(
        mood=mood,
        min_duration=min_duration,
        max_duration=max_duration,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        limit=limit,
    )
    return tracks


@app.post("/music/detect-mood")
async def detect_mood(text: str):
    """
    Detect appropriate music mood from script text.
    Returns recommended moods ranked by confidence.
    """
    moods = await _detect_content_mood(text)
    return {"moods": moods}


@app.post("/music/auto-select")
async def auto_select_music(
    script: str,
    duration: float,
    intensity: str = "medium",  # low, medium, high
):
    """
    Automatically select background music based on script content.
    """
    # Detect mood
    moods = await _detect_content_mood(script)

    if not moods:
        moods = [{"mood": MoodCategory.CORPORATE, "confidence": 0.5}]

    primary_mood = MoodCategory(moods[0]["mood"])

    # Search for tracks
    tracks = await search_music(
        mood=primary_mood,
        min_duration=int(duration),
        max_duration=int(duration * 2),
        limit=5,
    )

    if not tracks:
        # Fallback to any track
        tracks = await search_music(min_duration=int(duration), limit=5)

    return {
        "recommended_track": tracks[0] if tracks else None,
        "alternatives": tracks[1:] if len(tracks) > 1 else [],
        "detected_mood": primary_mood,
        "all_moods": moods,
    }


# ============================================================
# Sound Effects Endpoints
# ============================================================

@app.get("/sfx/search", response_model=List[SoundEffect])
async def search_sound_effects(
    query: str = Query(...),
    category: Optional[str] = None,
    max_duration: float = Query(10, description="Max duration in seconds"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search for sound effects."""
    effects = await _search_sfx_library(query, category, max_duration, limit)
    return effects


@app.get("/sfx/categories")
async def list_sfx_categories():
    """List available sound effect categories."""
    return {
        "categories": [
            "whoosh",
            "transition",
            "notification",
            "click",
            "pop",
            "swoosh",
            "impact",
            "ambient",
            "nature",
            "tech",
            "ui",
            "comedy",
        ]
    }


# ============================================================
# Brand Assets Endpoints
# ============================================================

@app.get("/brand/assets", response_model=List[BrandAsset])
async def list_brand_assets(
    asset_type: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """List brand assets."""
    assets = await _get_brand_assets(asset_type, user_id)
    return assets


@app.post("/brand/assets")
async def upload_brand_asset(
    name: str = Form(...),
    asset_type: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    """Upload a new brand asset."""
    asset_id = str(uuid.uuid4())

    # Save file
    output_dir = Path(os.getenv("BRAND_ASSETS_DIR", "/data/brand_assets"))
    output_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file.filename).suffix
    file_path = output_dir / f"{asset_id}{file_ext}"

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    asset = BrandAsset(
        id=asset_id,
        name=name,
        asset_type=asset_type,
        file_path=str(file_path),
        created_at=datetime.utcnow(),
    )

    # TODO: Save to database

    return asset


@app.delete("/brand/assets/{asset_id}")
async def delete_brand_asset(asset_id: str):
    """Delete a brand asset."""
    # TODO: Implement
    return {"status": "deleted"}


# ============================================================
# Helper Functions
# ============================================================

async def _search_pexels(
    query: str,
    orientation: str,
    min_duration: int,
    max_duration: int,
    limit: int,
) -> List[BRollResult]:
    """Search Pexels API for videos."""
    results = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.pexels.com/videos/search",
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": limit,
                    "size": "medium",
                },
                headers={"Authorization": PEXELS_API_KEY},
            )

            if response.status_code == 200:
                data = response.json()

                for video in data.get("videos", []):
                    duration = video.get("duration", 0)

                    if min_duration <= duration <= max_duration:
                        # Get best quality video file
                        video_files = video.get("video_files", [])
                        hd_file = next(
                            (f for f in video_files if f.get("quality") == "hd"),
                            video_files[0] if video_files else None
                        )

                        if hd_file:
                            results.append(BRollResult(
                                id=f"pexels_{video['id']}",
                                source="pexels",
                                url=hd_file["link"],
                                preview_url=video.get("video_pictures", [{}])[0].get("picture", ""),
                                thumbnail_url=video.get("image", ""),
                                duration=duration,
                                width=hd_file.get("width", 1920),
                                height=hd_file.get("height", 1080),
                                keywords=query.split(),
                                attribution=f"Video by {video.get('user', {}).get('name', 'Unknown')} from Pexels",
                            ))

    except Exception as e:
        logger.error(f"Pexels search error: {e}")

    return results


async def _search_pixabay(
    query: str,
    orientation: str,
    min_duration: int,
    max_duration: int,
    limit: int,
) -> List[BRollResult]:
    """Search Pixabay API for videos."""
    results = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://pixabay.com/api/videos/",
                params={
                    "key": PIXABAY_API_KEY,
                    "q": query,
                    "video_type": "film",
                    "per_page": limit,
                },
            )

            if response.status_code == 200:
                data = response.json()

                for video in data.get("hits", []):
                    duration = video.get("duration", 0)

                    if min_duration <= duration <= max_duration:
                        videos = video.get("videos", {})
                        large = videos.get("large", videos.get("medium", {}))

                        if large:
                            results.append(BRollResult(
                                id=f"pixabay_{video['id']}",
                                source="pixabay",
                                url=large.get("url", ""),
                                preview_url=video.get("picture_id", ""),
                                thumbnail_url=f"https://i.vimeocdn.com/video/{video.get('picture_id')}_640x360.jpg",
                                duration=duration,
                                width=large.get("width", 1920),
                                height=large.get("height", 1080),
                                keywords=video.get("tags", "").split(", "),
                                attribution="Video from Pixabay",
                            ))

    except Exception as e:
        logger.error(f"Pixabay search error: {e}")

    return results


async def _search_local_broll(
    query: str,
    orientation: str,
    min_duration: int,
    max_duration: int,
    limit: int,
) -> List[BRollResult]:
    """Search local B-roll library."""
    # TODO: Implement local library search
    return []


async def _extract_visual_keywords(text: str) -> List[str]:
    """Extract visual keywords from text using NLP."""
    # Simple keyword extraction (would use NLP in production)
    import re

    # Common visual concepts
    visual_patterns = [
        r'\b(office|business|meeting|team|work|computer|laptop|desk)\b',
        r'\b(nature|forest|mountain|ocean|beach|sky|sunset|sunrise)\b',
        r'\b(city|urban|building|street|traffic|downtown)\b',
        r'\b(technology|digital|data|code|programming|software)\b',
        r'\b(people|person|group|crowd|family|friends)\b',
        r'\b(money|finance|investment|growth|success)\b',
        r'\b(health|fitness|medical|hospital|doctor)\b',
        r'\b(food|cooking|restaurant|kitchen|eating)\b',
        r'\b(travel|vacation|journey|adventure|explore)\b',
        r'\b(education|learning|school|university|student)\b',
    ]

    keywords = []
    text_lower = text.lower()

    for pattern in visual_patterns:
        matches = re.findall(pattern, text_lower)
        keywords.extend(matches)

    # Remove duplicates and return
    return list(set(keywords))[:10]


def _split_script_sections(script: str) -> List[dict]:
    """Split script into sections for B-roll matching."""
    # Split by paragraphs or sentences
    paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]

    if not paragraphs:
        paragraphs = [script]

    return [{"text": p, "index": i} for i, p in enumerate(paragraphs)]


async def _search_music_library(
    mood: Optional[MoodCategory],
    min_duration: int,
    max_duration: int,
    bpm_min: Optional[int],
    bpm_max: Optional[int],
    limit: int,
) -> List[MusicTrack]:
    """Search music library."""
    # TODO: Implement actual music library
    # Return sample tracks for now
    sample_tracks = [
        MusicTrack(
            id="track_1",
            title="Corporate Success",
            artist="Royalty Free",
            duration=180,
            mood=MoodCategory.CORPORATE,
            bpm=120,
            source="local",
            url="/music/corporate_success.mp3",
            preview_url="/music/previews/corporate_success.mp3",
            license="Royalty Free",
        ),
        MusicTrack(
            id="track_2",
            title="Inspiring Journey",
            artist="Royalty Free",
            duration=240,
            mood=MoodCategory.INSPIRING,
            bpm=100,
            source="local",
            url="/music/inspiring_journey.mp3",
            preview_url="/music/previews/inspiring_journey.mp3",
            license="Royalty Free",
        ),
    ]

    if mood:
        sample_tracks = [t for t in sample_tracks if t.mood == mood]

    return sample_tracks[:limit]


async def _detect_content_mood(text: str) -> List[dict]:
    """Detect mood from text content."""
    text_lower = text.lower()

    mood_keywords = {
        MoodCategory.UPBEAT: ["exciting", "amazing", "great", "fantastic", "awesome"],
        MoodCategory.CALM: ["peaceful", "quiet", "gentle", "soft", "relaxing"],
        MoodCategory.DRAMATIC: ["urgent", "critical", "breaking", "shocking", "important"],
        MoodCategory.INSPIRING: ["success", "achieve", "dream", "goal", "inspire"],
        MoodCategory.HAPPY: ["happy", "joy", "celebrate", "fun", "smile"],
        MoodCategory.CORPORATE: ["business", "company", "professional", "enterprise", "corporate"],
        MoodCategory.ENERGETIC: ["energy", "power", "dynamic", "active", "fast"],
    }

    scores = {}

    for mood, keywords in mood_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[mood] = score

    # Sort by score
    sorted_moods = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [
        {"mood": mood.value, "confidence": score / 5}
        for mood, score in sorted_moods
    ]


async def _search_sfx_library(
    query: str,
    category: Optional[str],
    max_duration: float,
    limit: int,
) -> List[SoundEffect]:
    """Search sound effects library."""
    # TODO: Implement actual SFX library
    return []


async def _get_brand_assets(
    asset_type: Optional[str],
    user_id: Optional[str],
) -> List[BrandAsset]:
    """Get brand assets from storage."""
    # TODO: Implement database query
    return []


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "media-library",
        "pexels_configured": bool(PEXELS_API_KEY),
        "pixabay_configured": bool(PIXABAY_API_KEY),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5012)
