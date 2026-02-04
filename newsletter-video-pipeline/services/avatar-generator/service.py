"""
Avatar Generator Service Implementation using MuseTalk + LivePortrait.

This service runs on the Windows GPU server (RTX 5090) and provides:
- Avatar creation from video reference
- Audio-driven talking head video generation
- Face enhancement and natural motion
"""

import os
import json
import time
import uuid
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import asyncio
from concurrent.futures import ThreadPoolExecutor

import torch
import numpy as np
from loguru import logger

# Conditional imports for GPU models
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from .models import (
    AvatarModel,
    CreateAvatarRequest,
    CreateAvatarResponse,
    GenerateVideoRequest,
    GenerateVideoResponse,
    GenerateVideoProgress,
    AvatarListResponse,
    AvatarDeleteResponse,
    HealthResponse,
    OutputResolution,
    AspectRatio,
)


class AvatarGeneratorService:
    """Avatar generation service using MuseTalk + LivePortrait."""

    VERSION = "1.0.0"

    # Resolution mappings
    RESOLUTION_MAP = {
        OutputResolution.SD: (854, 480),
        OutputResolution.HD: (1280, 720),
        OutputResolution.FHD: (1920, 1080),
        OutputResolution.QHD: (2560, 1440),
        OutputResolution.UHD: (3840, 2160),
    }

    def __init__(
        self,
        musetalk_path: str = "/models/musetalk",
        liveportrait_path: str = "/models/liveportrait",
        avatars_dir: str = "/data/avatars",
        temp_dir: str = "/tmp/avatar_generator",
        device: str = "cuda",
    ):
        self.musetalk_path = Path(musetalk_path)
        self.liveportrait_path = Path(liveportrait_path)
        self.avatars_dir = Path(avatars_dir)
        self.temp_dir = Path(temp_dir)
        self.device = device

        # Create directories
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Model instances
        self.musetalk_model = None
        self.liveportrait_model = None
        self.face_detector = None

        # State
        self._avatars_cache: dict[str, AvatarModel] = {}
        self._default_avatar_id: Optional[str] = None
        self._progress_callbacks: dict[str, Callable] = {}

        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Load existing avatars
        self._load_avatars_metadata()

    def _load_avatars_metadata(self):
        """Load avatars metadata from disk."""
        metadata_file = self.avatars_dir / "avatars_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    data = json.load(f)
                    for avatar_data in data.get("avatars", []):
                        avatar = AvatarModel(**avatar_data)
                        self._avatars_cache[avatar.id] = avatar
                    self._default_avatar_id = data.get("default_avatar_id")
                logger.info(f"Loaded {len(self._avatars_cache)} avatar(s) from metadata")
            except Exception as e:
                logger.error(f"Failed to load avatars metadata: {e}")

    def _save_avatars_metadata(self):
        """Save avatars metadata to disk."""
        metadata_file = self.avatars_dir / "avatars_metadata.json"
        data = {
            "avatars": [a.model_dump() for a in self._avatars_cache.values()],
            "default_avatar_id": self._default_avatar_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        with open(metadata_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def initialize(self):
        """Initialize models."""
        logger.info("Initializing Avatar Generator Service...")

        # Check GPU
        if self.device == "cuda" and torch.cuda.is_available():
            logger.info(f"GPU available: {torch.cuda.get_device_name(0)}")
            logger.info(
                f"GPU Memory: {torch.cuda.memory_allocated(0) / 1e9:.2f}GB / "
                f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB"
            )
        else:
            logger.warning("CUDA not available, using CPU (will be slow)")
            self.device = "cpu"

        # Initialize face detector (MediaPipe or OpenCV)
        await self._init_face_detector()

        # Initialize MuseTalk
        await self._init_musetalk()

        # Initialize LivePortrait
        await self._init_liveportrait()

        logger.info("Avatar Generator Service initialized")

    async def _init_face_detector(self):
        """Initialize face detection model."""
        try:
            import mediapipe as mp
            self.face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=1,  # Full range model
                min_detection_confidence=0.5
            )
            logger.info("MediaPipe face detector initialized")
        except ImportError:
            logger.warning("MediaPipe not available, using OpenCV face detector")
            if CV2_AVAILABLE:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self.face_detector = cv2.CascadeClassifier(cascade_path)

    async def _init_musetalk(self):
        """Initialize MuseTalk model."""
        try:
            # MuseTalk initialization
            # The actual implementation depends on the MuseTalk repository structure
            # This is a placeholder for the actual model loading

            musetalk_script = self.musetalk_path / "inference.py"
            if musetalk_script.exists():
                logger.info("MuseTalk model path verified")
                self.musetalk_model = {"path": str(self.musetalk_path), "loaded": True}
            else:
                logger.warning(f"MuseTalk not found at {self.musetalk_path}")
                self.musetalk_model = None

        except Exception as e:
            logger.error(f"Failed to initialize MuseTalk: {e}")
            self.musetalk_model = None

    async def _init_liveportrait(self):
        """Initialize LivePortrait model."""
        try:
            # LivePortrait initialization
            liveportrait_script = self.liveportrait_path / "inference.py"
            if liveportrait_script.exists():
                logger.info("LivePortrait model path verified")
                self.liveportrait_model = {"path": str(self.liveportrait_path), "loaded": True}
            else:
                logger.warning(f"LivePortrait not found at {self.liveportrait_path}")
                self.liveportrait_model = None

        except Exception as e:
            logger.error(f"Failed to initialize LivePortrait: {e}")
            self.liveportrait_model = None

    async def create_avatar(
        self,
        video_path: Path,
        request: CreateAvatarRequest,
    ) -> CreateAvatarResponse:
        """
        Create an avatar from a reference video.

        Args:
            video_path: Path to the reference video
            request: Creation request parameters

        Returns:
            CreateAvatarResponse with avatar ID and metadata
        """
        start_time = time.time()

        # Generate avatar ID
        avatar_id = str(uuid.uuid4())[:8]

        # Create avatar directory
        avatar_dir = self.avatars_dir / avatar_id
        avatar_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating avatar {avatar_id} from video: {video_path}")

        try:
            # Copy source video
            source_video = avatar_dir / f"source{video_path.suffix}"
            shutil.copy2(video_path, source_video)

            # Get video info
            video_info = await self._get_video_info(source_video)
            duration = video_info.get("duration", 0)

            # Extract and validate face
            face_detected = await self._extract_face_data(avatar_dir, source_video)

            if not face_detected:
                raise ValueError("No face detected in video. Please use a video with a clear face view.")

            # Extract motion data for MuseTalk
            await self._extract_motion_data(avatar_dir, source_video)

            # Remove background if requested
            if request.remove_background:
                await self._remove_background(avatar_dir, source_video)

            # Create avatar model
            avatar = AvatarModel(
                id=avatar_id,
                name=request.name,
                description=request.description,
                source_video_duration_sec=duration,
                is_default=request.set_as_default,
                face_detected=face_detected,
                has_body=request.extract_body,
                background_removed=request.remove_background,
                motion_data_path=str(avatar_dir / "motion_data.pkl"),
                face_embedding_path=str(avatar_dir / "face_embedding.npy"),
            )

            # Save to cache
            self._avatars_cache[avatar_id] = avatar
            if request.set_as_default:
                self._default_avatar_id = avatar_id
            self._save_avatars_metadata()

            processing_time = time.time() - start_time

            logger.info(
                f"Avatar created: {avatar_id} ({request.name}), "
                f"duration: {duration:.2f}s, processing: {processing_time:.2f}s"
            )

            return CreateAvatarResponse(
                avatar_id=avatar_id,
                name=request.name,
                message=f"Avatar created successfully from {duration:.1f}s video",
                source_duration_sec=duration,
                face_detected=face_detected,
                processing_time_sec=processing_time,
            )

        except Exception as e:
            # Cleanup on failure
            if avatar_dir.exists():
                shutil.rmtree(avatar_dir)
            logger.error(f"Failed to create avatar: {e}")
            raise

    async def _get_video_info(self, video_path: Path) -> dict:
        """Get video metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get("format", {}).get("duration", 0))

                # Get video stream info
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        return {
                            "duration": duration,
                            "width": stream.get("width"),
                            "height": stream.get("height"),
                            "fps": eval(stream.get("r_frame_rate", "30/1")),
                        }

                return {"duration": duration}
        except Exception as e:
            logger.warning(f"Failed to get video info: {e}")

        return {"duration": 0}

    async def _extract_face_data(self, avatar_dir: Path, video_path: Path) -> bool:
        """Extract face data from video for avatar creation."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV not available, skipping face extraction")
            return True  # Assume face is present

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return False

            face_detected = False
            frame_count = 0
            face_frames = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1

                # Sample every 10th frame
                if frame_count % 10 != 0:
                    continue

                # Detect face
                if hasattr(self.face_detector, 'process'):
                    # MediaPipe
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self.face_detector.process(rgb_frame)
                    if results.detections:
                        face_detected = True
                        face_frames.append(frame)
                else:
                    # OpenCV cascade
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = self.face_detector.detectMultiScale(gray, 1.1, 4)
                    if len(faces) > 0:
                        face_detected = True
                        face_frames.append(frame)

            cap.release()

            # Save sample face frames
            if face_frames:
                for i, frame in enumerate(face_frames[:5]):
                    cv2.imwrite(str(avatar_dir / f"face_sample_{i}.jpg"), frame)

            return face_detected

        except Exception as e:
            logger.error(f"Face extraction failed: {e}")
            return False

    async def _extract_motion_data(self, avatar_dir: Path, video_path: Path):
        """Extract motion data for lip-sync animation."""
        # This would use MuseTalk's preprocessing
        # For now, create a placeholder
        motion_data = {
            "video_path": str(video_path),
            "extracted_at": datetime.utcnow().isoformat(),
        }

        import pickle
        with open(avatar_dir / "motion_data.pkl", "wb") as f:
            pickle.dump(motion_data, f)

    async def _remove_background(self, avatar_dir: Path, video_path: Path):
        """Remove background from video frames."""
        # This would use rembg or similar
        logger.info("Background removal requested (placeholder)")

    async def generate_video(
        self,
        request: GenerateVideoRequest,
        progress_callback: Optional[Callable[[GenerateVideoProgress], None]] = None,
    ) -> GenerateVideoResponse:
        """
        Generate a video with the avatar speaking the audio.

        Args:
            request: Generation request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            GenerateVideoResponse with video path and metadata
        """
        start_time = time.time()
        job_id = str(uuid.uuid4())[:8]

        # Get avatar
        avatar_id = request.avatar_id or self._default_avatar_id
        if not avatar_id:
            raise ValueError("No avatar specified and no default avatar set")

        if avatar_id not in self._avatars_cache:
            raise ValueError(f"Avatar not found: {avatar_id}")

        avatar = self._avatars_cache[avatar_id]
        avatar_dir = self.avatars_dir / avatar_id

        # Validate audio file
        audio_path = Path(request.audio_path)
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.info(
            f"Generating video with avatar {avatar_id}, "
            f"resolution: {request.resolution.value}, fps: {request.fps}"
        )

        # Report progress
        def report_progress(step: str, percent: float):
            if progress_callback:
                progress = GenerateVideoProgress(
                    job_id=job_id,
                    status="processing",
                    progress_percent=percent,
                    current_step=step,
                    estimated_remaining_sec=None,
                )
                progress_callback(progress)

        try:
            report_progress("Preparing audio", 5)

            # Get output dimensions
            width, height = self.RESOLUTION_MAP.get(
                request.resolution,
                self.RESOLUTION_MAP[OutputResolution.FHD]
            )

            # Adjust for aspect ratio
            if request.aspect_ratio == AspectRatio.PORTRAIT:
                width, height = height, width
            elif request.aspect_ratio == AspectRatio.SQUARE:
                size = min(width, height)
                width, height = size, size

            # Create temp working directory
            work_dir = self.temp_dir / job_id
            work_dir.mkdir(parents=True, exist_ok=True)

            report_progress("Running lip-sync generation", 20)

            # Run MuseTalk inference
            output_video = await self._run_musetalk(
                avatar_dir=avatar_dir,
                audio_path=audio_path,
                output_dir=work_dir,
                width=width,
                height=height,
                fps=request.fps,
                progress_callback=lambda p: report_progress("Lip-sync generation", 20 + p * 0.5),
            )

            # Apply LivePortrait enhancement if requested
            if request.use_liveportrait and self.liveportrait_model:
                report_progress("Applying motion enhancement", 75)
                output_video = await self._run_liveportrait(
                    input_video=output_video,
                    avatar_dir=avatar_dir,
                    output_dir=work_dir,
                )

            # Apply face enhancement if requested
            if request.enhance_face:
                report_progress("Enhancing face quality", 85)
                output_video = await self._enhance_face(output_video, work_dir)

            report_progress("Finalizing video", 95)

            # Move to output location
            final_filename = f"{job_id}.{request.output_format}"
            final_path = self.temp_dir / final_filename
            shutil.move(output_video, final_path)

            # Cleanup work directory
            shutil.rmtree(work_dir, ignore_errors=True)

            # Get output info
            video_info = await self._get_video_info(final_path)
            file_size_mb = final_path.stat().st_size / (1024 * 1024)

            processing_time = time.time() - start_time

            report_progress("Complete", 100)

            logger.info(
                f"Video generated: {final_filename}, "
                f"duration: {video_info.get('duration', 0):.2f}s, "
                f"size: {file_size_mb:.2f}MB, "
                f"processing: {processing_time:.2f}s"
            )

            return GenerateVideoResponse(
                video_url=f"/video/{final_filename}",
                video_path=str(final_path),
                duration_sec=video_info.get("duration", 0),
                resolution=f"{width}x{height}",
                fps=request.fps,
                file_size_mb=file_size_mb,
                avatar_id=avatar_id,
                processing_time_sec=processing_time,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            # Cleanup
            work_dir = self.temp_dir / job_id
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
            raise

    async def _run_musetalk(
        self,
        avatar_dir: Path,
        audio_path: Path,
        output_dir: Path,
        width: int,
        height: int,
        fps: int,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Path:
        """Run MuseTalk for lip-sync generation."""

        output_video = output_dir / "musetalk_output.mp4"

        # Get source video from avatar
        source_videos = list(avatar_dir.glob("source.*"))
        if not source_videos:
            raise ValueError("Avatar source video not found")
        source_video = source_videos[0]

        if self.musetalk_model and (self.musetalk_path / "inference.py").exists():
            # Run actual MuseTalk inference
            cmd = [
                "python",
                str(self.musetalk_path / "inference.py"),
                "--video_path", str(source_video),
                "--audio_path", str(audio_path),
                "--output_path", str(output_video),
                "--fps", str(fps),
            ]

            logger.info(f"Running MuseTalk: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"MuseTalk failed: {stderr.decode()}")
                raise RuntimeError(f"MuseTalk inference failed: {stderr.decode()}")

        else:
            # Fallback: create video from source + audio using FFmpeg
            logger.warning("MuseTalk not available, using FFmpeg fallback")

            # Get audio duration
            audio_info_cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(audio_path)
            ]
            result = subprocess.run(audio_info_cmd, capture_output=True, text=True)
            audio_duration = 10  # default
            if result.returncode == 0:
                data = json.loads(result.stdout)
                audio_duration = float(data.get("format", {}).get("duration", 10))

            # Create video with FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",  # Loop source video
                "-i", str(source_video),
                "-i", str(audio_path),
                "-t", str(audio_duration),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-r", str(fps),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-map", "0:v:0",
                "-map", "1:a:0",
                str(output_video),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {stderr.decode()}")

        if progress_callback:
            progress_callback(1.0)

        return output_video

    async def _run_liveportrait(
        self,
        input_video: Path,
        avatar_dir: Path,
        output_dir: Path,
    ) -> Path:
        """Run LivePortrait for motion enhancement."""
        output_video = output_dir / "liveportrait_output.mp4"

        if self.liveportrait_model and (self.liveportrait_path / "inference.py").exists():
            cmd = [
                "python",
                str(self.liveportrait_path / "inference.py"),
                "--source", str(input_video),
                "--output", str(output_video),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning(f"LivePortrait failed, using original: {stderr.decode()}")
                return input_video

            return output_video
        else:
            logger.warning("LivePortrait not available, skipping enhancement")
            return input_video

    async def _enhance_face(self, video_path: Path, output_dir: Path) -> Path:
        """Apply face enhancement to video."""
        # This would use GFPGAN or CodeFormer
        # For now, just return the original
        logger.info("Face enhancement requested (placeholder)")
        return video_path

    async def list_avatars(self) -> AvatarListResponse:
        """List all available avatars."""
        return AvatarListResponse(
            avatars=list(self._avatars_cache.values()),
            default_avatar_id=self._default_avatar_id,
            total_count=len(self._avatars_cache),
        )

    async def get_avatar(self, avatar_id: str) -> Optional[AvatarModel]:
        """Get a specific avatar by ID."""
        return self._avatars_cache.get(avatar_id)

    async def delete_avatar(self, avatar_id: str) -> AvatarDeleteResponse:
        """Delete an avatar."""
        if avatar_id not in self._avatars_cache:
            return AvatarDeleteResponse(
                avatar_id=avatar_id,
                message="Avatar not found",
                success=False,
            )

        # Remove from cache
        del self._avatars_cache[avatar_id]

        # Update default
        if self._default_avatar_id == avatar_id:
            self._default_avatar_id = None

        # Delete directory
        avatar_dir = self.avatars_dir / avatar_id
        if avatar_dir.exists():
            shutil.rmtree(avatar_dir)

        self._save_avatars_metadata()

        return AvatarDeleteResponse(
            avatar_id=avatar_id,
            message="Avatar deleted successfully",
            success=True,
        )

    async def set_default_avatar(self, avatar_id: str) -> bool:
        """Set the default avatar."""
        if avatar_id not in self._avatars_cache:
            return False

        self._default_avatar_id = avatar_id

        for aid, avatar in self._avatars_cache.items():
            avatar.is_default = (aid == avatar_id)

        self._save_avatars_metadata()
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
        if not self.musetalk_model and not self.liveportrait_model:
            status = "degraded"

        return HealthResponse(
            status=status,
            musetalk_loaded=self.musetalk_model is not None,
            liveportrait_loaded=self.liveportrait_model is not None,
            gpu_available=gpu_available,
            gpu_memory_used_gb=gpu_memory_used,
            gpu_memory_total_gb=gpu_memory_total,
            avatars_count=len(self._avatars_cache),
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        self._executor.shutdown(wait=False)

        # Clear temp files
        if self.temp_dir.exists():
            for f in self.temp_dir.iterdir():
                if f.is_file():
                    f.unlink()

        logger.info("Avatar generator service cleaned up")
