"""
Voice Cloner Service Implementation using XTTS-v2.

This service runs on the Windows GPU server (RTX 5090) and provides:
- Voice cloning from audio samples
- Text-to-speech synthesis with cloned voices
- Streaming audio generation
"""

import os
import json
import time
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, AsyncGenerator
import asyncio
from concurrent.futures import ThreadPoolExecutor

import torch
import torchaudio
import numpy as np
from loguru import logger

# XTTS imports (from coqui-tts)
try:
    from TTS.api import TTS
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    XTTS_AVAILABLE = True
except ImportError:
    XTTS_AVAILABLE = False
    logger.warning("XTTS not available. Install with: pip install coqui-tts")

from .models import (
    VoiceModel,
    VoiceCloneRequest,
    VoiceCloneResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    VoiceListResponse,
    VoiceDeleteResponse,
    HealthResponse,
    VoiceLanguage,
)


class VoiceClonerService:
    """Voice cloning and synthesis service using XTTS-v2."""

    VERSION = "1.0.0"

    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        voices_dir: str = "/data/voices",
        temp_dir: str = "/tmp/voice_cloner",
        device: str = "cuda",
        use_deepspeed: bool = True,
    ):
        self.model_name = model_name
        self.voices_dir = Path(voices_dir)
        self.temp_dir = Path(temp_dir)
        self.device = device
        self.use_deepspeed = use_deepspeed

        # Create directories
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Model and state
        self.model: Optional[Xtts] = None
        self.config: Optional[XttsConfig] = None
        self.tts: Optional[TTS] = None
        self._voices_cache: dict[str, VoiceModel] = {}
        self._default_voice_id: Optional[str] = None

        # Thread pool for CPU-bound operations
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Load existing voices metadata
        self._load_voices_metadata()

    def _load_voices_metadata(self):
        """Load voices metadata from disk."""
        metadata_file = self.voices_dir / "voices_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    data = json.load(f)
                    for voice_data in data.get("voices", []):
                        voice = VoiceModel(**voice_data)
                        self._voices_cache[voice.id] = voice
                    self._default_voice_id = data.get("default_voice_id")
                logger.info(f"Loaded {len(self._voices_cache)} voice(s) from metadata")
            except Exception as e:
                logger.error(f"Failed to load voices metadata: {e}")

    def _save_voices_metadata(self):
        """Save voices metadata to disk."""
        metadata_file = self.voices_dir / "voices_metadata.json"
        data = {
            "voices": [v.model_dump() for v in self._voices_cache.values()],
            "default_voice_id": self._default_voice_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        with open(metadata_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def initialize(self):
        """Initialize the XTTS model."""
        if not XTTS_AVAILABLE:
            raise RuntimeError("XTTS not available. Install with: pip install coqui-tts")

        logger.info(f"Initializing XTTS model: {self.model_name}")
        logger.info(f"Device: {self.device}, DeepSpeed: {self.use_deepspeed}")

        try:
            # Initialize TTS with XTTS model
            self.tts = TTS(model_name=self.model_name, progress_bar=True)

            # Move to GPU if available
            if self.device == "cuda" and torch.cuda.is_available():
                self.tts.to(self.device)
                logger.info(f"Model loaded on GPU: {torch.cuda.get_device_name(0)}")
                logger.info(
                    f"GPU Memory: {torch.cuda.memory_allocated(0) / 1e9:.2f}GB / "
                    f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB"
                )
            else:
                logger.warning("CUDA not available, using CPU")
                self.device = "cpu"

            logger.info("XTTS model initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize XTTS model: {e}")
            raise

    async def clone_voice(
        self,
        audio_files: list[Path],
        request: VoiceCloneRequest,
    ) -> VoiceCloneResponse:
        """
        Clone a voice from audio samples.

        Args:
            audio_files: List of paths to audio files
            request: Clone request parameters

        Returns:
            VoiceCloneResponse with voice ID and metadata
        """
        if not audio_files:
            raise ValueError("At least one audio file is required")

        # Generate voice ID
        voice_id = str(uuid.uuid4())[:8]

        # Create voice directory
        voice_dir = self.voices_dir / voice_id
        voice_dir.mkdir(parents=True, exist_ok=True)

        # Process and save audio samples
        total_duration = 0.0
        processed_samples = []

        for i, audio_file in enumerate(audio_files):
            try:
                # Load and validate audio
                waveform, sample_rate = torchaudio.load(audio_file)

                # Resample to 22050 Hz if needed (XTTS requirement)
                if sample_rate != 22050:
                    resampler = torchaudio.transforms.Resample(sample_rate, 22050)
                    waveform = resampler(waveform)
                    sample_rate = 22050

                # Convert to mono if stereo
                if waveform.shape[0] > 1:
                    waveform = waveform.mean(dim=0, keepdim=True)

                # Calculate duration
                duration = waveform.shape[1] / sample_rate
                total_duration += duration

                # Save processed sample
                sample_path = voice_dir / f"sample_{i:03d}.wav"
                torchaudio.save(sample_path, waveform, sample_rate)
                processed_samples.append(sample_path)

                logger.info(f"Processed sample {i+1}/{len(audio_files)}: {duration:.2f}s")

            except Exception as e:
                logger.error(f"Failed to process audio file {audio_file}: {e}")
                raise ValueError(f"Invalid audio file: {e}")

        # Determine quality estimate
        if total_duration < 10:
            quality = "basic"
        elif total_duration < 60:
            quality = "good"
        else:
            quality = "excellent"

        # Create voice model metadata
        voice_model = VoiceModel(
            id=voice_id,
            name=request.name,
            description=request.description,
            language=request.language,
            sample_duration_sec=total_duration,
            is_default=request.set_as_default,
        )

        # Save to cache and disk
        self._voices_cache[voice_id] = voice_model
        if request.set_as_default:
            self._default_voice_id = voice_id
        self._save_voices_metadata()

        # Save sample paths for synthesis
        samples_index = voice_dir / "samples.json"
        with open(samples_index, "w") as f:
            json.dump([str(p) for p in processed_samples], f)

        logger.info(
            f"Voice cloned successfully: {voice_id} ({request.name}), "
            f"duration: {total_duration:.2f}s, quality: {quality}"
        )

        return VoiceCloneResponse(
            voice_id=voice_id,
            name=request.name,
            message=f"Voice cloned successfully with {len(processed_samples)} sample(s)",
            sample_duration_sec=total_duration,
            estimated_quality=quality,
        )

    async def synthesize(self, request: SynthesizeRequest) -> SynthesizeResponse:
        """
        Synthesize speech from text using a cloned voice.

        Args:
            request: Synthesis request parameters

        Returns:
            SynthesizeResponse with audio file path and metadata
        """
        if not self.tts:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        start_time = time.time()

        # Get voice ID
        voice_id = request.voice_id or self._default_voice_id
        if not voice_id:
            raise ValueError("No voice specified and no default voice set")

        if voice_id not in self._voices_cache:
            raise ValueError(f"Voice not found: {voice_id}")

        voice = self._voices_cache[voice_id]
        voice_dir = self.voices_dir / voice_id

        # Get speaker samples
        samples_index = voice_dir / "samples.json"
        if not samples_index.exists():
            raise ValueError(f"Voice samples not found for: {voice_id}")

        with open(samples_index, "r") as f:
            sample_paths = json.load(f)

        if not sample_paths:
            raise ValueError(f"No samples found for voice: {voice_id}")

        # Use first sample as speaker reference
        speaker_wav = sample_paths[0]

        # Determine language
        language = request.language.value if request.language else voice.language.value

        # Generate output path
        output_filename = f"{uuid.uuid4()}.{request.output_format}"
        output_path = self.temp_dir / output_filename

        logger.info(
            f"Synthesizing {len(request.text)} chars with voice {voice_id} ({language})"
        )

        try:
            # Run synthesis in thread pool to not block event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._synthesize_sync,
                request.text,
                speaker_wav,
                language,
                str(output_path),
                request.speed,
                request.temperature,
                request.top_p,
                request.top_k,
                request.repetition_penalty,
                request.length_penalty,
            )

            # Get audio duration
            waveform, sample_rate = torchaudio.load(output_path)
            duration = waveform.shape[1] / sample_rate

            processing_time = time.time() - start_time

            logger.info(
                f"Synthesis complete: {duration:.2f}s audio in {processing_time:.2f}s "
                f"(RTF: {processing_time/duration:.2f}x)"
            )

            return SynthesizeResponse(
                audio_url=f"/audio/{output_filename}",
                audio_path=str(output_path),
                duration_sec=duration,
                voice_id=voice_id,
                language=language,
                text_length=len(request.text),
                processing_time_sec=processing_time,
            )

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise

    def _synthesize_sync(
        self,
        text: str,
        speaker_wav: str,
        language: str,
        output_path: str,
        speed: float,
        temperature: float,
        top_p: float,
        top_k: int,
        repetition_penalty: float,
        length_penalty: float,
    ):
        """Synchronous synthesis (runs in thread pool)."""
        self.tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=output_path,
            speed=speed,
        )

    async def synthesize_stream(
        self, request: SynthesizeRequest
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized audio chunks.

        Args:
            request: Synthesis request parameters

        Yields:
            Audio data chunks (WAV format)
        """
        if not self.tts:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        voice_id = request.voice_id or self._default_voice_id
        if not voice_id or voice_id not in self._voices_cache:
            raise ValueError(f"Voice not found: {voice_id}")

        voice = self._voices_cache[voice_id]
        voice_dir = self.voices_dir / voice_id

        with open(voice_dir / "samples.json", "r") as f:
            sample_paths = json.load(f)

        speaker_wav = sample_paths[0]
        language = request.language.value if request.language else voice.language.value

        # Split text into sentences for streaming
        sentences = self._split_into_sentences(request.text)

        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            # Generate audio for this sentence
            temp_file = self.temp_dir / f"stream_{uuid.uuid4()}.wav"

            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._synthesize_sync,
                    sentence,
                    speaker_wav,
                    language,
                    str(temp_file),
                    request.speed,
                    request.temperature,
                    request.top_p,
                    request.top_k,
                    request.repetition_penalty,
                    request.length_penalty,
                )

                # Read and yield audio data
                with open(temp_file, "rb") as f:
                    audio_data = f.read()
                    yield audio_data

            finally:
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences for streaming."""
        import re

        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    async def list_voices(self) -> VoiceListResponse:
        """List all available cloned voices."""
        return VoiceListResponse(
            voices=list(self._voices_cache.values()),
            default_voice_id=self._default_voice_id,
            total_count=len(self._voices_cache),
        )

    async def get_voice(self, voice_id: str) -> Optional[VoiceModel]:
        """Get a specific voice by ID."""
        return self._voices_cache.get(voice_id)

    async def delete_voice(self, voice_id: str) -> VoiceDeleteResponse:
        """Delete a cloned voice."""
        if voice_id not in self._voices_cache:
            return VoiceDeleteResponse(
                voice_id=voice_id,
                message="Voice not found",
                success=False,
            )

        # Remove from cache
        del self._voices_cache[voice_id]

        # Update default if needed
        if self._default_voice_id == voice_id:
            self._default_voice_id = None

        # Delete voice directory
        voice_dir = self.voices_dir / voice_id
        if voice_dir.exists():
            import shutil
            shutil.rmtree(voice_dir)

        # Save metadata
        self._save_voices_metadata()

        return VoiceDeleteResponse(
            voice_id=voice_id,
            message="Voice deleted successfully",
            success=True,
        )

    async def set_default_voice(self, voice_id: str) -> bool:
        """Set the default voice."""
        if voice_id not in self._voices_cache:
            return False

        self._default_voice_id = voice_id

        # Update voice models
        for vid, voice in self._voices_cache.items():
            voice.is_default = (vid == voice_id)

        self._save_voices_metadata()
        return True

    async def health_check(self) -> HealthResponse:
        """Check service health."""
        gpu_available = torch.cuda.is_available()
        gpu_memory_used = None
        gpu_memory_total = None

        if gpu_available:
            gpu_memory_used = torch.cuda.memory_allocated(0) / 1e9
            gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / 1e9

        status = "healthy"
        if not self.tts:
            status = "unhealthy"
        elif not gpu_available and self.device == "cuda":
            status = "degraded"

        return HealthResponse(
            status=status,
            model_loaded=self.tts is not None,
            gpu_available=gpu_available,
            gpu_memory_used_gb=gpu_memory_used,
            gpu_memory_total_gb=gpu_memory_total,
            voices_count=len(self._voices_cache),
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        self._executor.shutdown(wait=False)

        # Clear temp files
        import shutil
        if self.temp_dir.exists():
            for f in self.temp_dir.iterdir():
                if f.is_file():
                    f.unlink()

        logger.info("Voice cloner service cleaned up")
