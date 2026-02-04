"""
Video Processor Service Implementation using FFmpeg.

This service runs on the Linux VM and provides:
- Video format conversion for multiple platforms
- Resolution/aspect ratio adjustment
- Caption/subtitle addition
- Watermarking
- Audio normalization
- Shorts generation from long-form content
"""

import os
import json
import time
import uuid
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from .models import (
    ProcessVideoRequest,
    ProcessVideoResponse,
    VideoOutput,
    VideoInfoResponse,
    HealthResponse,
    Platform,
    VideoFormat,
    CaptionStyle,
)


class VideoProcessorService:
    """Video processing service using FFmpeg."""

    VERSION = "1.0.0"

    # Platform-specific settings
    PLATFORM_SPECS = {
        Platform.YOUTUBE: {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "bitrate": "8M",
            "audio_bitrate": "192k",
            "max_duration": None,  # No limit
            "aspect_ratio": "16:9",
        },
        Platform.YOUTUBE_SHORTS: {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "bitrate": "5M",
            "audio_bitrate": "128k",
            "max_duration": 60,
            "aspect_ratio": "9:16",
        },
        Platform.TIKTOK: {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "bitrate": "6M",
            "audio_bitrate": "128k",
            "max_duration": 600,  # 10 minutes
            "aspect_ratio": "9:16",
        },
        Platform.INSTAGRAM: {
            "width": 1080,
            "height": 1080,
            "fps": 30,
            "bitrate": "5M",
            "audio_bitrate": "128k",
            "max_duration": 60,
            "aspect_ratio": "1:1",
        },
        Platform.INSTAGRAM_REELS: {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "bitrate": "5M",
            "audio_bitrate": "128k",
            "max_duration": 90,
            "aspect_ratio": "9:16",
        },
        Platform.X_TWITTER: {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "bitrate": "5M",
            "audio_bitrate": "128k",
            "max_duration": 140,  # 2:20
            "aspect_ratio": "16:9",
        },
    }

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        output_dir: str = "/data/videos/output",
        temp_dir: str = "/tmp/video_processor",
    ):
        self.ffmpeg_path = ffmpeg_path
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=4)

        # FFmpeg info
        self._ffmpeg_version: Optional[str] = None

    async def initialize(self):
        """Initialize the service and verify FFmpeg."""
        logger.info("Initializing Video Processor Service...")

        # Check FFmpeg
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Extract version
                lines = result.stdout.split("\n")
                if lines:
                    self._ffmpeg_version = lines[0]
                logger.info(f"FFmpeg available: {self._ffmpeg_version}")
            else:
                logger.error("FFmpeg not available")
        except Exception as e:
            logger.error(f"FFmpeg check failed: {e}")

        logger.info("Video Processor Service initialized")

    async def process_video(self, request: ProcessVideoRequest) -> ProcessVideoResponse:
        """
        Process a video for specified platform(s).

        Args:
            request: Processing request parameters

        Returns:
            ProcessVideoResponse with output files
        """
        start_time = time.time()

        input_path = Path(request.input_path)
        if not input_path.exists():
            raise ValueError(f"Input video not found: {input_path}")

        # Get input video info
        input_info = await self.get_video_info(str(input_path))

        logger.info(
            f"Processing video: {input_path.name}, "
            f"duration: {input_info.duration_sec:.2f}s, "
            f"platforms: {[p.value for p in request.platforms]}"
        )

        # Determine output directory
        output_dir = Path(request.output_dir) if request.output_dir else self.temp_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine platforms to process
        if Platform.ALL in request.platforms:
            platforms = [p for p in Platform if p != Platform.ALL]
        else:
            platforms = request.platforms

        outputs = []
        shorts = []

        # Process for each platform
        for platform in platforms:
            try:
                output = await self._process_for_platform(
                    input_path=input_path,
                    platform=platform,
                    output_dir=output_dir,
                    request=request,
                )
                outputs.append(output)
                logger.info(f"Processed for {platform.value}: {output.filename}")
            except Exception as e:
                logger.error(f"Failed to process for {platform.value}: {e}")

        # Generate shorts if requested
        if request.generate_shorts:
            try:
                generated_shorts = await self._generate_shorts(
                    input_path=input_path,
                    output_dir=output_dir,
                    max_duration=request.shorts_max_duration,
                    count=request.shorts_count,
                )
                shorts.extend(generated_shorts)
                logger.info(f"Generated {len(generated_shorts)} shorts")
            except Exception as e:
                logger.error(f"Failed to generate shorts: {e}")

        processing_time = time.time() - start_time

        return ProcessVideoResponse(
            outputs=outputs,
            shorts=shorts,
            processing_time_sec=processing_time,
            input_duration_sec=input_info.duration_sec,
            message=f"Processed video for {len(outputs)} platform(s), "
                    f"generated {len(shorts)} short(s)",
        )

    async def _process_for_platform(
        self,
        input_path: Path,
        platform: Platform,
        output_dir: Path,
        request: ProcessVideoRequest,
    ) -> VideoOutput:
        """Process video for a specific platform."""

        specs = self.PLATFORM_SPECS[platform]
        output_filename = f"{input_path.stem}_{platform.value}.{request.output_format.value}"
        output_path = output_dir / output_filename

        # Build FFmpeg filter chain
        filters = []

        # Scale and pad to target resolution while maintaining aspect ratio
        target_w, target_h = specs["width"], specs["height"]
        filters.append(
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
        )

        # FPS adjustment
        filters.append(f"fps={specs['fps']}")

        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite
            "-i", str(input_path),
        ]

        # Handle intro
        concat_inputs = []
        if request.add_intro and request.intro_path:
            cmd.extend(["-i", request.intro_path])
            concat_inputs.append("intro")

        concat_inputs.append("main")

        # Handle outro
        if request.add_outro and request.outro_path:
            cmd.extend(["-i", request.outro_path])
            concat_inputs.append("outro")

        # Video filters
        filter_str = ",".join(filters)

        # Audio normalization
        audio_filters = []
        if request.normalize_audio:
            audio_filters.append(f"loudnorm=I={request.target_loudness}:TP=-1.5:LRA=11")

        # Build complex filter if needed
        if len(concat_inputs) > 1:
            # Complex concat filter
            complex_filter = self._build_concat_filter(
                concat_inputs, filter_str, audio_filters, specs
            )
            cmd.extend(["-filter_complex", complex_filter])
            cmd.extend(["-map", "[outv]", "-map", "[outa]"])
        else:
            cmd.extend(["-vf", filter_str])
            if audio_filters:
                cmd.extend(["-af", ",".join(audio_filters)])

        # Duration limit
        if specs["max_duration"]:
            cmd.extend(["-t", str(specs["max_duration"])])

        # Output settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-b:v", specs["bitrate"],
            "-maxrate", specs["bitrate"],
            "-bufsize", str(int(specs["bitrate"].replace("M", "")) * 2) + "M",
            "-c:a", "aac",
            "-b:a", specs["audio_bitrate"],
            "-movflags", "+faststart",
            str(output_path),
        ])

        # Run FFmpeg
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {stderr.decode()[-500:]}")

        # Get output info
        output_info = await self.get_video_info(str(output_path))

        return VideoOutput(
            platform=platform,
            path=str(output_path),
            filename=output_filename,
            resolution=f"{specs['width']}x{specs['height']}",
            duration_sec=output_info.duration_sec,
            file_size_mb=output_path.stat().st_size / (1024 * 1024),
            fps=specs["fps"],
            bitrate=specs["bitrate"],
        )

    def _build_concat_filter(
        self,
        inputs: list[str],
        video_filter: str,
        audio_filters: list[str],
        specs: dict,
    ) -> str:
        """Build FFmpeg complex filter for concatenation."""
        parts = []
        input_idx = 0

        for i, input_type in enumerate(inputs):
            # Scale each input to target size
            parts.append(
                f"[{input_idx}:v]scale={specs['width']}:{specs['height']}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={specs['width']}:{specs['height']}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={specs['fps']}[v{i}]"
            )
            input_idx += 1

        # Concat video
        video_inputs = "".join(f"[v{i}]" for i in range(len(inputs)))
        parts.append(f"{video_inputs}concat=n={len(inputs)}:v=1:a=0[outv]")

        # Concat audio
        audio_inputs = "".join(f"[{i}:a]" for i in range(len(inputs)))
        audio_filter_str = ",".join(audio_filters) if audio_filters else ""
        if audio_filter_str:
            parts.append(f"{audio_inputs}concat=n={len(inputs)}:v=0:a=1,{audio_filter_str}[outa]")
        else:
            parts.append(f"{audio_inputs}concat=n={len(inputs)}:v=0:a=1[outa]")

        return ";".join(parts)

    async def _generate_shorts(
        self,
        input_path: Path,
        output_dir: Path,
        max_duration: int,
        count: int,
    ) -> list[VideoOutput]:
        """Generate short clips from long-form video."""

        # Get input info
        input_info = await self.get_video_info(str(input_path))
        total_duration = input_info.duration_sec

        if total_duration <= max_duration:
            logger.warning("Video too short for shorts generation")
            return []

        shorts = []
        segment_duration = min(max_duration, total_duration / count)

        # Calculate segment start times (evenly distributed)
        for i in range(count):
            start_time = (total_duration - segment_duration) * i / max(count - 1, 1)

            output_filename = f"{input_path.stem}_short_{i+1}.mp4"
            output_path = output_dir / output_filename

            # Use TIKTOK specs for shorts
            specs = self.PLATFORM_SPECS[Platform.TIKTOK]

            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss", str(start_time),
                "-i", str(input_path),
                "-t", str(segment_duration),
                "-vf", f"scale={specs['width']}:{specs['height']}:"
                       f"force_original_aspect_ratio=decrease,"
                       f"pad={specs['width']}:{specs['height']}:(ow-iw)/2:(oh-ih)/2,"
                       f"fps={specs['fps']}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-b:v", specs["bitrate"],
                "-c:a", "aac",
                "-b:a", specs["audio_bitrate"],
                "-movflags", "+faststart",
                str(output_path),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode == 0:
                output_info = await self.get_video_info(str(output_path))
                shorts.append(VideoOutput(
                    platform=Platform.TIKTOK,
                    path=str(output_path),
                    filename=output_filename,
                    resolution=f"{specs['width']}x{specs['height']}",
                    duration_sec=output_info.duration_sec,
                    file_size_mb=output_path.stat().st_size / (1024 * 1024),
                    fps=specs["fps"],
                    bitrate=specs["bitrate"],
                ))
            else:
                logger.error(f"Failed to generate short {i+1}: {stderr.decode()[-200:]}")

        return shorts

    async def get_video_info(self, video_path: str) -> VideoInfoResponse:
        """Get video metadata."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError("ffprobe failed")

            data = json.loads(result.stdout)
            format_info = data.get("format", {})

            # Find video and audio streams
            video_stream = None
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream

            if not video_stream:
                raise ValueError("No video stream found")

            # Parse frame rate
            fps_str = video_stream.get("r_frame_rate", "30/1")
            try:
                num, den = map(int, fps_str.split("/"))
                fps = num / den
            except:
                fps = 30.0

            return VideoInfoResponse(
                path=video_path,
                duration_sec=float(format_info.get("duration", 0)),
                width=video_stream.get("width", 0),
                height=video_stream.get("height", 0),
                fps=fps,
                codec=video_stream.get("codec_name", "unknown"),
                bitrate=format_info.get("bit_rate"),
                file_size_mb=int(format_info.get("size", 0)) / (1024 * 1024),
                has_audio=audio_stream is not None,
                audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            )

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            raise

    async def health_check(self) -> HealthResponse:
        """Check service health."""
        # Check temp dir is writable
        temp_writable = False
        try:
            test_file = self.temp_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            temp_writable = True
        except:
            pass

        return HealthResponse(
            status="healthy" if self._ffmpeg_version and temp_writable else "degraded",
            ffmpeg_available=self._ffmpeg_version is not None,
            ffmpeg_version=self._ffmpeg_version,
            temp_dir_writable=temp_writable,
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
        logger.info("Video processor service cleaned up")
