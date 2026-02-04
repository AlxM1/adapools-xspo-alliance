"""
Audio transcription with word-level timestamps.

Uses Whisper for speech recognition with precise word timing.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx


class TranscriptionWord:
    """Word with timing information."""

    def __init__(self, word: str, start: float, end: float, confidence: float = 1.0):
        self.word = word
        self.start = start
        self.end = end
        self.confidence = confidence


class TranscriptionResult:
    """Full transcription with word-level timing."""

    def __init__(
        self,
        text: str,
        words: list[TranscriptionWord],
        duration: float,
        language: str = "en",
    ):
        self.text = text
        self.words = words
        self.duration = duration
        self.language = language


class Transcriber:
    """Transcribe audio with word-level timestamps."""

    def __init__(self):
        self.whisper_url = os.getenv("WHISPER_URL", "http://localhost:9000")
        self.gpu_host = os.getenv("GPU_HOST", "localhost")
        self._model = None

    async def transcribe(self, audio_path: str, language: str = "en") -> TranscriptionResult:
        """
        Transcribe audio file with word-level timestamps.

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'en', 'es', 'fr')

        Returns:
            TranscriptionResult with word-level timing
        """
        # Try GPU server first (faster-whisper)
        try:
            return await self._transcribe_remote(audio_path, language)
        except Exception as e:
            print(f"Remote transcription failed: {e}, falling back to local")

        # Fallback to local Whisper
        return await self._transcribe_local(audio_path, language)

    async def _transcribe_remote(self, audio_path: str, language: str) -> TranscriptionResult:
        """Transcribe using remote GPU server."""
        async with httpx.AsyncClient(timeout=300) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"http://{self.gpu_host}:9000/transcribe",
                    files={"audio_file": f},
                    data={"language": language, "word_timestamps": "true"},
                )

            if response.status_code != 200:
                raise Exception(f"Transcription failed: {response.status_code}")

            result = response.json()

        # Parse response
        words = []
        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                words.append(TranscriptionWord(
                    word=word_data["word"].strip(),
                    start=word_data["start"],
                    end=word_data["end"],
                    confidence=word_data.get("probability", 1.0),
                ))

        return TranscriptionResult(
            text=result.get("text", ""),
            words=words,
            duration=result.get("duration", words[-1].end if words else 0),
            language=language,
        )

    async def _transcribe_local(self, audio_path: str, language: str) -> TranscriptionResult:
        """Transcribe using local Whisper."""
        try:
            import whisper
        except ImportError:
            raise Exception("Whisper not installed. Run: pip install openai-whisper")

        # Load model if not already loaded
        if self._model is None:
            self._model = whisper.load_model("base")

        # Run transcription in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
            )
        )

        # Parse result
        words = []
        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                words.append(TranscriptionWord(
                    word=word_data["word"].strip(),
                    start=word_data["start"],
                    end=word_data["end"],
                    confidence=word_data.get("probability", 1.0),
                ))

        duration = words[-1].end if words else 0

        return TranscriptionResult(
            text=result.get("text", ""),
            words=words,
            duration=duration,
            language=language,
        )

    async def transcribe_url(self, url: str, language: str = "en") -> TranscriptionResult:
        """Transcribe audio from URL."""
        # Download file first
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()

        # Save to temp file
        suffix = Path(url).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        try:
            return await self.transcribe(tmp_path, language)
        finally:
            os.unlink(tmp_path)

    async def generate_timing(self, text: str, duration: float) -> TranscriptionResult:
        """
        Generate word timing from text and duration.
        Used when no audio is available.

        Args:
            text: Full text to time
            duration: Total duration in seconds

        Returns:
            TranscriptionResult with estimated timing
        """
        # Split text into words
        raw_words = text.split()

        if not raw_words:
            return TranscriptionResult(
                text=text,
                words=[],
                duration=duration,
                language="en",
            )

        # Calculate timing based on word length and natural pacing
        # Average speaking rate: ~150 words per minute = 2.5 words/sec
        # But we'll weight by word length

        total_chars = sum(len(w) for w in raw_words)
        char_duration = duration / total_chars if total_chars > 0 else 0.1

        words = []
        current_time = 0.0

        for word in raw_words:
            word_duration = len(word) * char_duration

            # Add small pause between words
            pause = 0.05

            words.append(TranscriptionWord(
                word=word,
                start=current_time,
                end=current_time + word_duration,
            ))

            current_time += word_duration + pause

        # Scale to fit exact duration
        if words and words[-1].end > 0:
            scale = duration / words[-1].end
            for word in words:
                word.start *= scale
                word.end *= scale

        return TranscriptionResult(
            text=text,
            words=words,
            duration=duration,
            language="en",
        )
