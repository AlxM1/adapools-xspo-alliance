"""
Pipeline Orchestrator Service.

This is the main orchestration layer that coordinates:
1. Script Generation (Newsletter → Script)
2. Voice Synthesis (Script → Audio)
3. Avatar Video Generation (Audio → Video)
4. Video Processing (Video → Multi-platform formats)
5. Publishing (Upload to social platforms)
"""

import os
import json
import time
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import httpx

from loguru import logger

from .models import (
    PipelineRequest,
    PipelineResponse,
    PipelineJob,
    PipelineStatus,
    PipelineStage,
    StageResult,
    VideoOutput,
    PublishResult,
    ServiceStatus,
    SystemHealthResponse,
)


class PipelineOrchestrator:
    """Main orchestrator for the newsletter-to-video pipeline."""

    VERSION = "1.0.0"

    def __init__(
        self,
        # GPU server (Windows) endpoints
        voice_service_url: str = "http://192.168.1.100:5002",
        avatar_service_url: str = "http://192.168.1.100:5003",
        # Local (Linux VM) service endpoints
        video_processor_url: str = "http://localhost:5005",
        social_publisher_url: str = "http://localhost:5006",
        script_generator_url: str = "http://localhost:5007",
        # Storage
        output_dir: str = "/data/videos/output",
        temp_dir: str = "/tmp/pipeline",
    ):
        self.voice_service_url = voice_service_url
        self.avatar_service_url = avatar_service_url
        self.video_processor_url = video_processor_url
        self.social_publisher_url = social_publisher_url
        self.script_generator_url = script_generator_url

        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Job tracking
        self._jobs: dict[str, PipelineJob] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Initialize the orchestrator."""
        logger.info("Initializing Pipeline Orchestrator...")

        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

        # Check service health
        health = await self.health_check()
        healthy_count = len([s for s in health.services if s.status == "healthy"])
        logger.info(f"Pipeline Orchestrator initialized. {healthy_count}/{len(health.services)} services healthy")

    async def execute_pipeline(
        self,
        request: PipelineRequest,
        progress_callback: Optional[Callable[[PipelineResponse], None]] = None,
    ) -> PipelineResponse:
        """
        Execute the full newsletter-to-video pipeline.

        Args:
            request: Pipeline request with all parameters
            progress_callback: Optional callback for progress updates

        Returns:
            PipelineResponse with all outputs and results
        """
        job_id = str(uuid.uuid4())[:12]
        job = PipelineJob(
            job_id=job_id,
            request=request,
            status=PipelineStatus.PENDING,
        )
        self._jobs[job_id] = job

        logger.info(f"Starting pipeline job {job_id}")

        def update_progress(stage: PipelineStage, percent: float, status: PipelineStatus):
            job.current_stage = stage
            job.progress_percent = percent
            job.status = status
            if progress_callback:
                progress_callback(self._job_to_response(job))

        try:
            # Stage 1: Script Generation
            update_progress(PipelineStage.SCRIPT, 5, PipelineStatus.GENERATING_SCRIPT)
            script_result = await self._generate_scripts(request, job)
            job.stages.append(script_result)

            if script_result.status != "success":
                raise RuntimeError(f"Script generation failed: {script_result.error_message}")

            # Stage 2: Voice Synthesis
            update_progress(PipelineStage.VOICE, 25, PipelineStatus.SYNTHESIZING_VOICE)
            voice_result = await self._synthesize_voice(request, job)
            job.stages.append(voice_result)

            if voice_result.status != "success":
                raise RuntimeError(f"Voice synthesis failed: {voice_result.error_message}")

            # Stage 3: Avatar Video Generation
            update_progress(PipelineStage.AVATAR, 45, PipelineStatus.GENERATING_VIDEO)
            avatar_result = await self._generate_avatar_video(request, job)
            job.stages.append(avatar_result)

            if avatar_result.status != "success":
                raise RuntimeError(f"Avatar generation failed: {avatar_result.error_message}")

            # Stage 4: Video Processing
            update_progress(PipelineStage.VIDEO_PROCESS, 70, PipelineStatus.PROCESSING_VIDEO)
            process_result = await self._process_videos(request, job)
            job.stages.append(process_result)

            if process_result.status != "success":
                raise RuntimeError(f"Video processing failed: {process_result.error_message}")

            # Stage 5: Publishing (if enabled)
            if request.auto_publish and request.publish_platforms:
                update_progress(PipelineStage.PUBLISH, 90, PipelineStatus.PUBLISHING)
                publish_result = await self._publish_videos(request, job)
                job.stages.append(publish_result)
            else:
                job.stages.append(StageResult(
                    stage=PipelineStage.PUBLISH,
                    status="skipped",
                    duration_sec=0,
                ))

            # Complete
            job.status = PipelineStatus.COMPLETED
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()

            logger.info(f"Pipeline job {job_id} completed successfully")

            # Send webhook if configured
            if request.webhook_url:
                await self._send_webhook(request.webhook_url, job)

        except Exception as e:
            logger.exception(f"Pipeline job {job_id} failed: {e}")
            job.status = PipelineStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()

        return self._job_to_response(job)

    async def _generate_scripts(
        self,
        request: PipelineRequest,
        job: PipelineJob,
    ) -> StageResult:
        """Stage 1: Generate scripts from newsletter content."""
        start_time = time.time()

        try:
            response = await self._http_client.post(
                f"{self.script_generator_url}/generate",
                json={
                    "newsletter_content": request.newsletter_content,
                    "newsletter_title": request.newsletter_title,
                    "newsletter_url": request.newsletter_url,
                    "format": "both" if request.generate_long_form and request.generate_shorts else (
                        "long_form" if request.generate_long_form else "short_form"
                    ),
                    "tone": request.script_tone,
                    "include_cta": request.include_cta,
                    "custom_instructions": request.custom_instructions,
                },
            )

            if response.status_code != 200:
                raise RuntimeError(f"Script service error: {response.text}")

            data = response.json()

            # Store script outputs
            if data.get("long_form"):
                job.outputs["script_long_form"] = data["long_form"]["full_script"]
                job.outputs["script_long_form_data"] = data["long_form"]

            if data.get("shorts_clips"):
                job.outputs["script_shorts"] = [
                    clip["full_script"] for clip in data["shorts_clips"]
                ]
                job.outputs["script_shorts_data"] = data["shorts_clips"]
            elif data.get("short_form"):
                job.outputs["script_shorts"] = [data["short_form"]["full_script"]]
                job.outputs["script_shorts_data"] = [data["short_form"]]

            return StageResult(
                stage=PipelineStage.SCRIPT,
                status="success",
                duration_sec=time.time() - start_time,
                output_data={"tokens_used": data.get("tokens_used", 0)},
            )

        except Exception as e:
            return StageResult(
                stage=PipelineStage.SCRIPT,
                status="failed",
                duration_sec=time.time() - start_time,
                error_message=str(e),
            )

    async def _synthesize_voice(
        self,
        request: PipelineRequest,
        job: PipelineJob,
    ) -> StageResult:
        """Stage 2: Synthesize voice audio from scripts."""
        start_time = time.time()

        try:
            audio_files = []

            # Synthesize long-form script
            if request.generate_long_form and job.outputs.get("script_long_form"):
                response = await self._http_client.post(
                    f"{self.voice_service_url}/synthesize",
                    json={
                        "text": job.outputs["script_long_form"],
                        "voice_id": request.voice_id,
                        "output_format": "wav",
                    },
                )

                if response.status_code != 200:
                    raise RuntimeError(f"Voice service error: {response.text}")

                data = response.json()
                job.outputs["audio_long_form"] = data["audio_path"]
                audio_files.append(("long_form", data["audio_path"]))

            # Synthesize shorts
            if request.generate_shorts and job.outputs.get("script_shorts"):
                shorts_audio = []
                for i, script in enumerate(job.outputs["script_shorts"][:request.shorts_count]):
                    response = await self._http_client.post(
                        f"{self.voice_service_url}/synthesize",
                        json={
                            "text": script,
                            "voice_id": request.voice_id,
                            "output_format": "wav",
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        shorts_audio.append(data["audio_path"])
                        audio_files.append((f"short_{i+1}", data["audio_path"]))

                job.outputs["audio_shorts"] = shorts_audio

            return StageResult(
                stage=PipelineStage.VOICE,
                status="success",
                duration_sec=time.time() - start_time,
                output_data={"audio_files": len(audio_files)},
            )

        except Exception as e:
            return StageResult(
                stage=PipelineStage.VOICE,
                status="failed",
                duration_sec=time.time() - start_time,
                error_message=str(e),
            )

    async def _generate_avatar_video(
        self,
        request: PipelineRequest,
        job: PipelineJob,
    ) -> StageResult:
        """Stage 3: Generate avatar videos from audio."""
        start_time = time.time()

        try:
            videos = []

            # Generate long-form video
            if job.outputs.get("audio_long_form"):
                response = await self._http_client.post(
                    f"{self.avatar_service_url}/generate",
                    json={
                        "avatar_id": request.avatar_id,
                        "audio_path": job.outputs["audio_long_form"],
                        "resolution": "1080p",
                        "aspect_ratio": "16:9",
                        "fps": 30,
                    },
                )

                if response.status_code != 200:
                    raise RuntimeError(f"Avatar service error: {response.text}")

                data = response.json()
                job.outputs["video_long_form"] = data["video_path"]
                videos.append(VideoOutput(
                    video_type="long_form",
                    video_path=data["video_path"],
                    duration_sec=data["duration_sec"],
                    file_size_mb=data["file_size_mb"],
                ))

            # Generate short videos
            if job.outputs.get("audio_shorts"):
                shorts_videos = []
                for i, audio_path in enumerate(job.outputs["audio_shorts"]):
                    response = await self._http_client.post(
                        f"{self.avatar_service_url}/generate",
                        json={
                            "avatar_id": request.avatar_id,
                            "audio_path": audio_path,
                            "resolution": "1080p",
                            "aspect_ratio": "9:16",  # Vertical for shorts
                            "fps": 30,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        shorts_videos.append(data["video_path"])
                        videos.append(VideoOutput(
                            video_type=f"short_{i+1}",
                            video_path=data["video_path"],
                            duration_sec=data["duration_sec"],
                            file_size_mb=data["file_size_mb"],
                        ))

                job.outputs["video_shorts"] = shorts_videos

            job.outputs["videos"] = videos

            return StageResult(
                stage=PipelineStage.AVATAR,
                status="success",
                duration_sec=time.time() - start_time,
                output_data={"videos_generated": len(videos)},
            )

        except Exception as e:
            return StageResult(
                stage=PipelineStage.AVATAR,
                status="failed",
                duration_sec=time.time() - start_time,
                error_message=str(e),
            )

    async def _process_videos(
        self,
        request: PipelineRequest,
        job: PipelineJob,
    ) -> StageResult:
        """Stage 4: Process videos for multiple platforms."""
        start_time = time.time()

        try:
            processed_videos = []

            for video in job.outputs.get("videos", []):
                response = await self._http_client.post(
                    f"{self.video_processor_url}/process",
                    json={
                        "input_path": video.video_path,
                        "platforms": request.target_platforms,
                        "normalize_audio": True,
                    },
                )

                if response.status_code == 200:
                    data = response.json()

                    # Update video with platform versions
                    platform_versions = {}
                    for output in data.get("outputs", []):
                        platform_versions[output["platform"]] = output["path"]

                    video.platform_versions = platform_versions
                    processed_videos.append(video)

            job.outputs["processed_videos"] = processed_videos

            return StageResult(
                stage=PipelineStage.VIDEO_PROCESS,
                status="success",
                duration_sec=time.time() - start_time,
                output_data={"processed_count": len(processed_videos)},
            )

        except Exception as e:
            return StageResult(
                stage=PipelineStage.VIDEO_PROCESS,
                status="failed",
                duration_sec=time.time() - start_time,
                error_message=str(e),
            )

    async def _publish_videos(
        self,
        request: PipelineRequest,
        job: PipelineJob,
    ) -> StageResult:
        """Stage 5: Publish videos to social platforms."""
        start_time = time.time()

        try:
            publish_results = []

            for video in job.outputs.get("processed_videos", []):
                # Get video title/description from script data
                if video.video_type == "long_form":
                    script_data = job.outputs.get("script_long_form_data", {})
                else:
                    idx = int(video.video_type.split("_")[1]) - 1
                    shorts_data = job.outputs.get("script_shorts_data", [])
                    script_data = shorts_data[idx] if idx < len(shorts_data) else {}

                title = script_data.get("title", request.newsletter_title or "Video")
                description = script_data.get("description", "")
                hashtags = script_data.get("hashtags", [])

                for platform in request.publish_platforms:
                    # Get platform-specific video path
                    video_path = video.platform_versions.get(platform, video.video_path)

                    response = await self._http_client.post(
                        f"{self.social_publisher_url}/publish",
                        json={
                            "video_path": video_path,
                            "platforms": [platform],
                            "title": title,
                            "description": description,
                            "tags": hashtags,
                            "privacy": request.publish_privacy,
                            "scheduled_time": request.scheduled_time.isoformat() if request.scheduled_time else None,
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        for result in data.get("results", []):
                            publish_results.append(PublishResult(
                                video_type=video.video_type,
                                platform=result["platform"],
                                status=result["status"],
                                video_id=result.get("video_id"),
                                video_url=result.get("video_url"),
                                error_message=result.get("error_message"),
                            ))

            job.outputs["publish_results"] = publish_results

            return StageResult(
                stage=PipelineStage.PUBLISH,
                status="success",
                duration_sec=time.time() - start_time,
                output_data={"published_count": len([r for r in publish_results if r.status == "published"])},
            )

        except Exception as e:
            return StageResult(
                stage=PipelineStage.PUBLISH,
                status="failed",
                duration_sec=time.time() - start_time,
                error_message=str(e),
            )

    async def _send_webhook(self, url: str, job: PipelineJob):
        """Send completion webhook."""
        try:
            await self._http_client.post(
                url,
                json=self._job_to_response(job).model_dump(),
                timeout=10,
            )
            logger.info(f"Webhook sent to {url}")
        except Exception as e:
            logger.warning(f"Failed to send webhook: {e}")

    def _job_to_response(self, job: PipelineJob) -> PipelineResponse:
        """Convert job to response object."""
        total_duration = None
        if job.completed_at and job.started_at:
            total_duration = (job.completed_at - job.started_at).total_seconds()

        return PipelineResponse(
            job_id=job.job_id,
            status=job.status,
            progress_percent=job.progress_percent,
            current_stage=job.current_stage.value if job.current_stage else None,
            stages=job.stages,
            script_long_form=job.outputs.get("script_long_form"),
            script_shorts=job.outputs.get("script_shorts", []),
            audio_path=job.outputs.get("audio_long_form"),
            videos=job.outputs.get("processed_videos", []),
            publish_results=job.outputs.get("publish_results", []),
            started_at=job.started_at,
            completed_at=job.completed_at,
            total_duration_sec=total_duration,
            error_message=job.error_message,
        )

    async def get_job(self, job_id: str) -> Optional[PipelineResponse]:
        """Get job status by ID."""
        job = self._jobs.get(job_id)
        if job:
            return self._job_to_response(job)
        return None

    async def list_jobs(self, limit: int = 50) -> list[PipelineResponse]:
        """List recent jobs."""
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.started_at,
            reverse=True,
        )[:limit]
        return [self._job_to_response(j) for j in jobs]

    async def health_check(self) -> SystemHealthResponse:
        """Check health of all services."""
        services = []

        # Check each service
        service_endpoints = [
            ("Voice Cloner (GPU)", self.voice_service_url),
            ("Avatar Generator (GPU)", self.avatar_service_url),
            ("Video Processor", self.video_processor_url),
            ("Social Publisher", self.social_publisher_url),
            ("Script Generator", self.script_generator_url),
        ]

        for name, url in service_endpoints:
            try:
                start = time.time()
                response = await self._http_client.get(f"{url}/health", timeout=5)
                latency = (time.time() - start) * 1000

                if response.status_code == 200:
                    status = "healthy"
                else:
                    status = "degraded"

            except Exception:
                status = "unhealthy"
                latency = None

            services.append(ServiceStatus(
                name=name,
                url=url,
                status=status,
                latency_ms=latency,
                last_check=datetime.utcnow(),
            ))

        # Determine overall status
        healthy_count = len([s for s in services if s.status == "healthy"])
        if healthy_count == len(services):
            overall_status = "healthy"
        elif healthy_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        # Count jobs
        active_jobs = len([j for j in self._jobs.values() if j.status not in [PipelineStatus.COMPLETED, PipelineStatus.FAILED]])
        completed_24h = len([
            j for j in self._jobs.values()
            if j.completed_at and (datetime.utcnow() - j.completed_at).total_seconds() < 86400
        ])

        return SystemHealthResponse(
            status=overall_status,
            services=services,
            active_jobs=active_jobs,
            completed_jobs_24h=completed_24h,
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Pipeline orchestrator cleaned up")
