"""
ASS (Advanced SubStation Alpha) subtitle generator.

Generates animated captions with various effects using ASS format,
which supports advanced styling and animations that work with FFmpeg.
"""

import re
from pathlib import Path
from typing import List


class ASSGenerator:
    """Generate ASS subtitle files with animated captions."""

    def __init__(self, config):
        self.config = config

        # Convert hex colors to ASS format (&HBBGGRR&)
        self.primary_color = self._hex_to_ass(config.primary_color)
        self.secondary_color = self._hex_to_ass(config.secondary_color)
        self.outline_color = self._hex_to_ass(config.outline_color)
        self.shadow_color = self._hex_to_ass(config.shadow_color)
        self.bg_color = self._hex_to_ass(config.background_color)

    def _hex_to_ass(self, hex_color: str) -> str:
        """Convert hex color (#RRGGBB) to ASS format (&HBBGGRR&)."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
            return f"&H{b}{g}{r}&"
        return "&HFFFFFF&"

    def _format_time(self, seconds: float) -> str:
        """Format seconds to ASS time format (H:MM:SS.CC)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        centiseconds = int((secs % 1) * 100)
        return f"{hours}:{minutes:02d}:{int(secs):02d}.{centiseconds:02d}"

    def _get_alignment(self) -> int:
        """Get ASS alignment value based on position."""
        # ASS alignment: 1-3 bottom, 4-6 middle, 7-9 top
        # 1=left, 2=center, 3=right
        position_map = {
            "bottom": 2,
            "center": 5,
            "top": 8,
        }
        return position_map.get(self.config.position, 2)

    async def generate(self, transcription, output_path: Path):
        """Generate ASS file from transcription."""
        lines = []

        # Header
        lines.append("[Script Info]")
        lines.append("Title: Generated Captions")
        lines.append("ScriptType: v4.00+")
        lines.append("Collisions: Normal")
        lines.append("PlayDepth: 0")
        lines.append("Timer: 100.0000")
        lines.append("WrapStyle: 0")
        lines.append("")

        # Styles
        lines.append("[V4+ Styles]")
        lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")

        # Main style
        bold = 1 if self.config.font_weight == "bold" else 0
        alignment = self._get_alignment()

        lines.append(
            f"Style: Default,{self.config.font_family},{self.config.font_size},"
            f"{self.primary_color},{self.secondary_color},{self.outline_color},{self.shadow_color},"
            f"{bold},0,0,0,100,100,0,0,1,{self.config.outline_width},{self.config.shadow_offset},"
            f"{alignment},10,10,{self.config.margin_bottom},1"
        )

        # Highlight style for karaoke
        lines.append(
            f"Style: Highlight,{self.config.font_family},{self.config.font_size},"
            f"{self.secondary_color},{self.primary_color},{self.outline_color},{self.shadow_color},"
            f"{bold},0,0,0,100,100,0,0,1,{self.config.outline_width},{self.config.shadow_offset},"
            f"{alignment},10,10,{self.config.margin_bottom},1"
        )

        lines.append("")

        # Events
        lines.append("[Events]")
        lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        # Generate caption events based on style
        style = self.config.style.value

        if style == "karaoke":
            events = self._generate_karaoke(transcription)
        elif style == "bounce":
            events = self._generate_bounce(transcription)
        elif style == "typewriter":
            events = self._generate_typewriter(transcription)
        elif style == "wave":
            events = self._generate_wave(transcription)
        elif style == "glow":
            events = self._generate_glow(transcription)
        elif style == "highlight":
            events = self._generate_highlight(transcription)
        else:  # minimal
            events = self._generate_minimal(transcription)

        lines.extend(events)

        # Write file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _group_words_into_lines(self, words) -> List[List]:
        """Group words into lines based on max_words_per_line."""
        lines = []
        current_line = []

        for word in words:
            current_line.append(word)

            if len(current_line) >= self.config.max_words_per_line:
                lines.append(current_line)
                current_line = []

        if current_line:
            lines.append(current_line)

        return lines

    def _generate_karaoke(self, transcription) -> List[str]:
        """Generate karaoke-style captions with word highlighting."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            # Build karaoke text with timing tags
            text_parts = []

            for i, word in enumerate(line_words):
                # Duration in centiseconds
                duration_cs = int((word.end - word.start) * 100)

                # Add karaoke timing tag
                # {\k<duration>} highlights the syllable for that duration
                text_parts.append(f"{{\\k{duration_cs}}}{word.word}")

            text = " ".join(text_parts)

            # Use {\kf} for smooth fill effect
            text = text.replace("\\k", "\\kf")

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.5)  # Add buffer

            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        return events

    def _generate_bounce(self, transcription) -> List[str]:
        """Generate bounce animation effect."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            for i, word in enumerate(line_words):
                # Calculate position based on word index
                # Use \an5 for center alignment and \pos for positioning

                # Bounce animation: scale from 0 to 120% to 100%
                word_start = word.start
                word_end = line_end + 0.3

                # Animation tags
                bounce_in = (
                    f"{{\\fscx0\\fscy0\\t({0},{100},\\fscx120\\fscy120)"
                    f"\\t({100},{200},\\fscx100\\fscy100)}}"
                )

                start_time = self._format_time(word_start)
                end_time = self._format_time(word_end)

                # Position each word
                x_offset = i * 150  # Approximate spacing
                text = f"{{\\an5\\pos(640,{720 - self.config.margin_bottom})}}{bounce_in}{word.word}"

                events.append(
                    f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
                )

        return events

    def _generate_typewriter(self, transcription) -> List[str]:
        """Generate typewriter effect."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            # Build line character by character
            full_text = " ".join(w.word for w in line_words)
            char_duration = (line_end - line_start) / len(full_text) if full_text else 0.1

            # Use clip animation to reveal text
            reveal_duration_ms = int((line_end - line_start) * 1000)

            # Typewriter uses \clip to reveal text progressively
            text = f"{{\\clip(0,0,0,1080)\\t(0,{reveal_duration_ms},\\clip(0,0,1920,1080))}}{full_text}"

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.5)

            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        return events

    def _generate_wave(self, transcription) -> List[str]:
        """Generate wavy text animation."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            full_text = " ".join(w.word for w in line_words)

            # Wave effect using transforms on each character
            # This is simplified - full implementation would animate each char
            wave_text = []

            for i, char in enumerate(full_text):
                if char == " ":
                    wave_text.append(" ")
                else:
                    # Offset each character's animation timing
                    delay = i * 50  # 50ms delay per character
                    wave_text.append(
                        f"{{\\t({delay},{delay + 200},\\frz10)"
                        f"\\t({delay + 200},{delay + 400},\\frz-10)"
                        f"\\t({delay + 400},{delay + 600},\\frz0)}}{char}"
                    )

            text = "".join(wave_text)

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.5)

            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        return events

    def _generate_glow(self, transcription) -> List[str]:
        """Generate glowing text effect."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            full_text = " ".join(w.word for w in line_words)

            # Glow effect using blur and color animation
            # Layer 1: Blurred glow background
            glow_text = (
                f"{{\\blur10\\3c{self.secondary_color}\\bord8}}{full_text}"
            )

            # Layer 2: Sharp text on top
            sharp_text = f"{{\\blur0}}{full_text}"

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.5)

            # Add glow layer (lower layer number = behind)
            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{glow_text}"
            )

            # Add sharp text layer
            events.append(
                f"Dialogue: 1,{start_time},{end_time},Default,,0,0,0,,{sharp_text}"
            )

        return events

    def _generate_highlight(self, transcription) -> List[str]:
        """Generate highlight box behind current word."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            # Full line text
            full_text = " ".join(w.word for w in line_words)

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.5)

            # Base text layer
            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{full_text}"
            )

            # Add highlight for each word
            for word in line_words:
                # Highlight box using \bord and alpha
                word_start = self._format_time(word.start)
                word_end = self._format_time(word.end)

                # Yellow highlight box behind word
                highlight_text = (
                    f"{{\\1c{self.secondary_color}\\bord0\\shad0"
                    f"\\3c{self.secondary_color}\\4c{self.secondary_color}"
                    f"\\be10}}{word.word}"
                )

                events.append(
                    f"Dialogue: 1,{word_start},{word_end},Highlight,,0,0,0,,{highlight_text}"
                )

        return events

    def _generate_minimal(self, transcription) -> List[str]:
        """Generate clean, minimal captions."""
        events = []
        word_lines = self._group_words_into_lines(transcription.words)

        for line_words in word_lines:
            if not line_words:
                continue

            line_start = line_words[0].start
            line_end = line_words[-1].end

            full_text = " ".join(w.word for w in line_words)

            # Simple fade in/out
            fade_duration = 150  # ms
            text = f"{{\\fad({fade_duration},{fade_duration})}}{full_text}"

            start_time = self._format_time(line_start)
            end_time = self._format_time(line_end + 0.2)

            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        return events
