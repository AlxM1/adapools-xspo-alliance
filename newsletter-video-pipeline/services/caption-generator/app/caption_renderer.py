"""
Caption renderer for multiple output formats and video burning.
"""

import asyncio
import json
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import List


class CaptionStyle(str, Enum):
    KARAOKE = "karaoke"
    BOUNCE = "bounce"
    TYPEWRITER = "typewriter"
    WAVE = "wave"
    GLOW = "glow"
    HIGHLIGHT = "highlight"
    MINIMAL = "minimal"


class CaptionRenderer:
    """Render captions in various formats."""

    def __init__(self):
        self.ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")

    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT time (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_vtt_time(self, seconds: float) -> str:
        """Format seconds to VTT time (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def _group_words(self, words, max_words: int = 6) -> List[List]:
        """Group words into caption lines."""
        lines = []
        current_line = []

        for word in words:
            current_line.append(word)

            if len(current_line) >= max_words:
                lines.append(current_line)
                current_line = []

        if current_line:
            lines.append(current_line)

        return lines

    async def generate_srt(self, transcription, config, output_path: Path):
        """Generate SRT subtitle file."""
        lines = []
        word_lines = self._group_words(
            transcription.words,
            config.max_words_per_line
        )

        for i, line_words in enumerate(word_lines, 1):
            if not line_words:
                continue

            start_time = self._format_srt_time(line_words[0].start)
            end_time = self._format_srt_time(line_words[-1].end + 0.2)
            text = " ".join(w.word for w in line_words)

            lines.append(str(i))
            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    async def generate_vtt(self, transcription, config, output_path: Path):
        """Generate WebVTT subtitle file."""
        lines = ["WEBVTT", ""]
        word_lines = self._group_words(
            transcription.words,
            config.max_words_per_line
        )

        for i, line_words in enumerate(word_lines, 1):
            if not line_words:
                continue

            start_time = self._format_vtt_time(line_words[0].start)
            end_time = self._format_vtt_time(line_words[-1].end + 0.2)
            text = " ".join(w.word for w in line_words)

            lines.append(str(i))
            lines.append(f"{start_time} --> {end_time}")

            # Add VTT styling based on config
            if config.position == "top":
                lines.append(f"<c.{config.style}>{text}</c>")
            else:
                lines.append(text)

            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    async def generate_json(self, transcription, config, output_path: Path):
        """Generate JSON caption data with all timing info."""
        word_lines = self._group_words(
            transcription.words,
            config.max_words_per_line
        )

        data = {
            "version": "1.0",
            "config": {
                "style": config.style.value,
                "font_family": config.font_family,
                "font_size": config.font_size,
                "primary_color": config.primary_color,
                "secondary_color": config.secondary_color,
            },
            "duration": transcription.duration,
            "language": transcription.language,
            "full_text": transcription.text,
            "lines": [],
            "words": [],
        }

        # Add line data
        for line_words in word_lines:
            if not line_words:
                continue

            data["lines"].append({
                "text": " ".join(w.word for w in line_words),
                "start": line_words[0].start,
                "end": line_words[-1].end,
                "word_count": len(line_words),
            })

        # Add word-level data
        for word in transcription.words:
            data["words"].append({
                "word": word.word,
                "start": word.start,
                "end": word.end,
                "confidence": word.confidence,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def burn_captions(
        self,
        video_path: Path,
        caption_path: Path,
        output_path: Path,
    ):
        """
        Burn captions onto video using FFmpeg.

        Args:
            video_path: Input video file
            caption_path: Caption file (ASS, SRT, or VTT)
            output_path: Output video file
        """
        caption_ext = caption_path.suffix.lower()

        if caption_ext == ".ass":
            # ASS files use the ass filter
            filter_str = f"ass='{caption_path}'"
        else:
            # SRT/VTT use subtitles filter
            filter_str = f"subtitles='{caption_path}'"

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {stderr.decode()}")

    async def preview_caption(
        self,
        text: str,
        config,
        duration: float = 5.0,
        output_path: Path = None,
    ) -> Path:
        """
        Generate a preview video with the caption style.

        Args:
            text: Sample text to display
            config: Caption configuration
            duration: Preview duration in seconds
            output_path: Output video path

        Returns:
            Path to preview video
        """
        if output_path is None:
            output_path = Path("/tmp") / f"preview_{config.style.value}.mp4"

        # Create black background video
        bg_cmd = [
            self.ffmpeg_path,
            "-f", "lavfi",
            "-i", f"color=c=black:s=1920x1080:d={duration}",
            "-c:v", "libx264",
            "-y",
            str(output_path.with_suffix(".temp.mp4")),
        ]

        process = await asyncio.create_subprocess_exec(
            *bg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        # TODO: Generate preview with captions
        # For now, return the background video
        return output_path.with_suffix(".temp.mp4")

    async def render_animated_text(
        self,
        text: str,
        config,
        timing: List[dict],
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        """
        Render animated text to video using moviepy.

        This provides more control over animations than ASS.
        """
        try:
            from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
        except ImportError:
            raise Exception("moviepy not installed. Run: pip install moviepy")

        # Create background
        duration = timing[-1]["end"] if timing else 5.0
        background = ColorClip(size=(width, height), color=(0, 0, 0), duration=duration)

        clips = [background]

        for word_data in timing:
            word = word_data["word"]
            start = word_data["start"]
            end = word_data["end"]

            # Create text clip
            txt_clip = (
                TextClip(
                    word,
                    fontsize=config.font_size,
                    font=config.font_family,
                    color=config.primary_color.lstrip("#"),
                    stroke_color=config.outline_color.lstrip("#"),
                    stroke_width=config.outline_width,
                )
                .set_start(start)
                .set_end(end + 0.3)
                .set_position("center")
            )

            clips.append(txt_clip)

        # Composite all clips
        video = CompositeVideoClip(clips)
        video.write_videofile(str(output_path), fps=fps)
