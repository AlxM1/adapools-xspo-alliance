"""
Social Publisher Service Implementation.

This service runs on the Linux VM and provides:
- YouTube video upload via Data API v3
- TikTok video upload via Content Posting API
- Instagram Reels upload via Graph API
- X/Twitter video upload via API v2
"""

import os
import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import asyncio
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from .models import (
    PublishRequest,
    PublishResponse,
    PlatformPublishResult,
    PublishProgress,
    PublishStatus,
    SocialPlatform,
    PrivacyStatus,
    OAuthStatusResponse,
    HealthResponse,
)


class SocialPublisherService:
    """Multi-platform social media publishing service."""

    VERSION = "1.0.0"

    def __init__(
        self,
        credentials_dir: str = "/data/credentials",
        temp_dir: str = "/tmp/social_publisher",
    ):
        self.credentials_dir = Path(credentials_dir)
        self.temp_dir = Path(temp_dir)

        # Create directories
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Platform clients (initialized lazily)
        self._youtube_client = None
        self._tiktok_client = None
        self._instagram_client = None
        self._x_client = None

        # Connection status
        self._platform_status: dict[SocialPlatform, bool] = {
            p: False for p in SocialPlatform
        }

        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def initialize(self):
        """Initialize the service and load credentials."""
        logger.info("Initializing Social Publisher Service...")

        # Check for existing credentials and initialize clients
        await self._init_youtube()
        await self._init_tiktok()
        await self._init_instagram()
        await self._init_x_twitter()

        connected = [p.value for p, c in self._platform_status.items() if c]
        logger.info(f"Social Publisher initialized. Connected platforms: {connected}")

    async def _init_youtube(self):
        """Initialize YouTube client."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds_file = self.credentials_dir / "youtube_credentials.json"
            if creds_file.exists():
                with open(creds_file, "r") as f:
                    creds_data = json.load(f)

                creds = Credentials.from_authorized_user_info(creds_data)
                self._youtube_client = build("youtube", "v3", credentials=creds)
                self._platform_status[SocialPlatform.YOUTUBE] = True
                logger.info("YouTube client initialized")
            else:
                logger.warning("YouTube credentials not found")

        except ImportError:
            logger.warning("Google API client not installed")
        except Exception as e:
            logger.error(f"Failed to initialize YouTube: {e}")

    async def _init_tiktok(self):
        """Initialize TikTok client."""
        try:
            creds_file = self.credentials_dir / "tiktok_credentials.json"
            if creds_file.exists():
                with open(creds_file, "r") as f:
                    creds_data = json.load(f)

                # Store access token for API calls
                self._tiktok_client = {
                    "access_token": creds_data.get("access_token"),
                    "open_id": creds_data.get("open_id"),
                }
                self._platform_status[SocialPlatform.TIKTOK] = True
                logger.info("TikTok client initialized")
            else:
                logger.warning("TikTok credentials not found")

        except Exception as e:
            logger.error(f"Failed to initialize TikTok: {e}")

    async def _init_instagram(self):
        """Initialize Instagram client."""
        try:
            from instagrapi import Client

            creds_file = self.credentials_dir / "instagram_credentials.json"
            if creds_file.exists():
                with open(creds_file, "r") as f:
                    creds_data = json.load(f)

                client = Client()

                # Try to load session
                session_file = self.credentials_dir / "instagram_session.json"
                if session_file.exists():
                    client.load_settings(session_file)
                else:
                    # Login
                    client.login(
                        creds_data.get("username"),
                        creds_data.get("password"),
                    )
                    client.dump_settings(session_file)

                self._instagram_client = client
                self._platform_status[SocialPlatform.INSTAGRAM] = True
                logger.info("Instagram client initialized")
            else:
                logger.warning("Instagram credentials not found")

        except ImportError:
            logger.warning("instagrapi not installed")
        except Exception as e:
            logger.error(f"Failed to initialize Instagram: {e}")

    async def _init_x_twitter(self):
        """Initialize X/Twitter client."""
        try:
            import tweepy

            creds_file = self.credentials_dir / "x_credentials.json"
            if creds_file.exists():
                with open(creds_file, "r") as f:
                    creds_data = json.load(f)

                # OAuth 1.0a for media upload
                auth = tweepy.OAuthHandler(
                    creds_data.get("api_key"),
                    creds_data.get("api_secret"),
                )
                auth.set_access_token(
                    creds_data.get("access_token"),
                    creds_data.get("access_token_secret"),
                )

                self._x_client = {
                    "api": tweepy.API(auth),
                    "client": tweepy.Client(
                        bearer_token=creds_data.get("bearer_token"),
                        consumer_key=creds_data.get("api_key"),
                        consumer_secret=creds_data.get("api_secret"),
                        access_token=creds_data.get("access_token"),
                        access_token_secret=creds_data.get("access_token_secret"),
                    ),
                }
                self._platform_status[SocialPlatform.X_TWITTER] = True
                logger.info("X/Twitter client initialized")
            else:
                logger.warning("X/Twitter credentials not found")

        except ImportError:
            logger.warning("tweepy not installed")
        except Exception as e:
            logger.error(f"Failed to initialize X/Twitter: {e}")

    async def publish(
        self,
        request: PublishRequest,
        progress_callback: Optional[Callable[[PublishProgress], None]] = None,
    ) -> PublishResponse:
        """
        Publish video to specified platform(s).

        Args:
            request: Publish request with video and metadata
            progress_callback: Optional callback for progress updates

        Returns:
            PublishResponse with results for each platform
        """
        job_id = str(uuid.uuid4())[:8]
        results = []

        video_path = Path(request.video_path)
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        logger.info(
            f"Publishing video to {len(request.platforms)} platform(s): "
            f"{[p.value for p in request.platforms]}"
        )

        # Publish to each platform
        for platform in request.platforms:
            try:
                if progress_callback:
                    progress_callback(PublishProgress(
                        job_id=job_id,
                        platform=platform,
                        status=PublishStatus.UPLOADING,
                        progress_percent=0,
                        message=f"Starting upload to {platform.value}",
                    ))

                if not self._platform_status.get(platform):
                    results.append(PlatformPublishResult(
                        platform=platform,
                        status=PublishStatus.FAILED,
                        error_message=f"{platform.value} not connected. Please authenticate first.",
                    ))
                    continue

                result = await self._publish_to_platform(
                    platform=platform,
                    request=request,
                    progress_callback=progress_callback,
                    job_id=job_id,
                )
                results.append(result)

            except Exception as e:
                logger.exception(f"Failed to publish to {platform.value}: {e}")
                results.append(PlatformPublishResult(
                    platform=platform,
                    status=PublishStatus.FAILED,
                    error_message=str(e),
                ))

        successful = len([r for r in results if r.status == PublishStatus.PUBLISHED])
        failed = len([r for r in results if r.status == PublishStatus.FAILED])

        return PublishResponse(
            job_id=job_id,
            results=results,
            successful_count=successful,
            failed_count=failed,
            message=f"Published to {successful}/{len(request.platforms)} platform(s)",
        )

    async def _publish_to_platform(
        self,
        platform: SocialPlatform,
        request: PublishRequest,
        progress_callback: Optional[Callable],
        job_id: str,
    ) -> PlatformPublishResult:
        """Publish to a specific platform."""

        if platform == SocialPlatform.YOUTUBE:
            return await self._publish_youtube(request, progress_callback, job_id)
        elif platform == SocialPlatform.TIKTOK:
            return await self._publish_tiktok(request, progress_callback, job_id)
        elif platform == SocialPlatform.INSTAGRAM:
            return await self._publish_instagram(request, progress_callback, job_id)
        elif platform == SocialPlatform.X_TWITTER:
            return await self._publish_x_twitter(request, progress_callback, job_id)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    async def _publish_youtube(
        self,
        request: PublishRequest,
        progress_callback: Optional[Callable],
        job_id: str,
    ) -> PlatformPublishResult:
        """Publish video to YouTube."""
        from googleapiclient.http import MediaFileUpload

        try:
            # Prepare metadata
            body = {
                "snippet": {
                    "title": request.title[:100],  # YouTube limit
                    "description": request.description[:5000],
                    "tags": request.youtube.tags if request.youtube else [],
                    "categoryId": request.youtube.category_id if request.youtube else "22",
                },
                "status": {
                    "privacyStatus": request.privacy.value,
                    "madeForKids": request.youtube.made_for_kids if request.youtube else False,
                    "embeddable": request.youtube.embeddable if request.youtube else True,
                    "license": request.youtube.license if request.youtube else "youtube",
                },
            }

            # Add schedule if specified
            if request.scheduled_time and request.privacy == PrivacyStatus.PRIVATE:
                body["status"]["publishAt"] = request.scheduled_time.isoformat() + "Z"

            # Create media upload
            media = MediaFileUpload(
                request.video_path,
                mimetype="video/*",
                resumable=True,
                chunksize=1024 * 1024,  # 1MB chunks
            )

            # Execute upload
            upload_request = self._youtube_client.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = upload_request.next_chunk()
                if status and progress_callback:
                    progress_callback(PublishProgress(
                        job_id=job_id,
                        platform=SocialPlatform.YOUTUBE,
                        status=PublishStatus.UPLOADING,
                        progress_percent=status.progress() * 100,
                        message=f"Uploading: {status.progress() * 100:.1f}%",
                    ))

            video_id = response["id"]
            video_url = f"https://youtube.com/watch?v={video_id}"

            # Upload thumbnail if provided
            if request.thumbnail_path and Path(request.thumbnail_path).exists():
                try:
                    self._youtube_client.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(request.thumbnail_path),
                    ).execute()
                except Exception as e:
                    logger.warning(f"Failed to upload thumbnail: {e}")

            # Add to playlist if specified
            if request.youtube and request.youtube.playlist_id:
                try:
                    self._youtube_client.playlistItems().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "playlistId": request.youtube.playlist_id,
                                "resourceId": {
                                    "kind": "youtube#video",
                                    "videoId": video_id,
                                },
                            },
                        },
                    ).execute()
                except Exception as e:
                    logger.warning(f"Failed to add to playlist: {e}")

            logger.info(f"Published to YouTube: {video_url}")

            return PlatformPublishResult(
                platform=SocialPlatform.YOUTUBE,
                status=PublishStatus.PUBLISHED,
                video_id=video_id,
                video_url=video_url,
                published_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return PlatformPublishResult(
                platform=SocialPlatform.YOUTUBE,
                status=PublishStatus.FAILED,
                error_message=str(e),
            )

    async def _publish_tiktok(
        self,
        request: PublishRequest,
        progress_callback: Optional[Callable],
        job_id: str,
    ) -> PlatformPublishResult:
        """Publish video to TikTok using Content Posting API."""
        import httpx

        try:
            access_token = self._tiktok_client["access_token"]
            open_id = self._tiktok_client["open_id"]

            # Step 1: Initialize video upload
            init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"

            # Prepare post info
            post_info = {
                "title": request.title[:150],  # TikTok limit
                "privacy_level": "PUBLIC_TO_EVERYONE" if request.privacy == PrivacyStatus.PUBLIC else "SELF_ONLY",
            }

            if request.tiktok:
                post_info["disable_comment"] = not request.tiktok.allow_comments
                post_info["disable_duet"] = not request.tiktok.allow_duet
                post_info["disable_stitch"] = not request.tiktok.allow_stitch

            # Get file size
            file_size = Path(request.video_path).stat().st_size

            async with httpx.AsyncClient() as client:
                init_response = await client.post(
                    init_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "post_info": post_info,
                        "source_info": {
                            "source": "FILE_UPLOAD",
                            "video_size": file_size,
                            "chunk_size": file_size,  # Single chunk
                            "total_chunk_count": 1,
                        },
                    },
                )

                init_data = init_response.json()
                if init_data.get("error", {}).get("code") != "ok":
                    raise ValueError(f"TikTok init failed: {init_data}")

                publish_id = init_data["data"]["publish_id"]
                upload_url = init_data["data"]["upload_url"]

                # Step 2: Upload video
                if progress_callback:
                    progress_callback(PublishProgress(
                        job_id=job_id,
                        platform=SocialPlatform.TIKTOK,
                        status=PublishStatus.UPLOADING,
                        progress_percent=30,
                        message="Uploading video to TikTok...",
                    ))

                with open(request.video_path, "rb") as f:
                    video_data = f.read()

                upload_response = await client.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                    },
                    content=video_data,
                )

                if upload_response.status_code != 201:
                    raise ValueError(f"TikTok upload failed: {upload_response.text}")

                # Step 3: Check publish status
                if progress_callback:
                    progress_callback(PublishProgress(
                        job_id=job_id,
                        platform=SocialPlatform.TIKTOK,
                        status=PublishStatus.PROCESSING,
                        progress_percent=80,
                        message="Processing video...",
                    ))

                status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

                # Poll for status
                for _ in range(30):  # Max 5 minutes
                    await asyncio.sleep(10)

                    status_response = await client.post(
                        status_url,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"publish_id": publish_id},
                    )

                    status_data = status_response.json()
                    pub_status = status_data.get("data", {}).get("status")

                    if pub_status == "PUBLISH_COMPLETE":
                        video_id = status_data.get("data", {}).get("video_id")
                        # TikTok doesn't return direct URL
                        video_url = f"https://www.tiktok.com/@{open_id}/video/{video_id}"

                        logger.info(f"Published to TikTok: {video_url}")

                        return PlatformPublishResult(
                            platform=SocialPlatform.TIKTOK,
                            status=PublishStatus.PUBLISHED,
                            video_id=video_id,
                            video_url=video_url,
                            published_at=datetime.utcnow(),
                        )

                    elif pub_status in ["FAILED", "PUBLISH_CANCELLED"]:
                        fail_reason = status_data.get("data", {}).get("fail_reason", "Unknown")
                        raise ValueError(f"TikTok publish failed: {fail_reason}")

                raise ValueError("TikTok publish timed out")

        except Exception as e:
            logger.error(f"TikTok upload failed: {e}")
            return PlatformPublishResult(
                platform=SocialPlatform.TIKTOK,
                status=PublishStatus.FAILED,
                error_message=str(e),
            )

    async def _publish_instagram(
        self,
        request: PublishRequest,
        progress_callback: Optional[Callable],
        job_id: str,
    ) -> PlatformPublishResult:
        """Publish video to Instagram as Reel."""

        try:
            if progress_callback:
                progress_callback(PublishProgress(
                    job_id=job_id,
                    platform=SocialPlatform.INSTAGRAM,
                    status=PublishStatus.UPLOADING,
                    progress_percent=30,
                    message="Uploading Reel to Instagram...",
                ))

            # Build caption with hashtags
            caption = request.title
            if request.description:
                caption += f"\n\n{request.description}"
            if request.tags:
                hashtags = " ".join(f"#{tag.replace('#', '')}" for tag in request.tags[:30])
                caption += f"\n\n{hashtags}"

            # Upload as Reel using instagrapi
            loop = asyncio.get_event_loop()
            media = await loop.run_in_executor(
                self._executor,
                lambda: self._instagram_client.clip_upload(
                    request.video_path,
                    caption[:2200],  # Instagram caption limit
                ),
            )

            video_id = media.pk
            video_url = f"https://www.instagram.com/reel/{media.code}/"

            logger.info(f"Published to Instagram: {video_url}")

            return PlatformPublishResult(
                platform=SocialPlatform.INSTAGRAM,
                status=PublishStatus.PUBLISHED,
                video_id=str(video_id),
                video_url=video_url,
                published_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Instagram upload failed: {e}")
            return PlatformPublishResult(
                platform=SocialPlatform.INSTAGRAM,
                status=PublishStatus.FAILED,
                error_message=str(e),
            )

    async def _publish_x_twitter(
        self,
        request: PublishRequest,
        progress_callback: Optional[Callable],
        job_id: str,
    ) -> PlatformPublishResult:
        """Publish video to X/Twitter."""

        try:
            if progress_callback:
                progress_callback(PublishProgress(
                    job_id=job_id,
                    platform=SocialPlatform.X_TWITTER,
                    status=PublishStatus.UPLOADING,
                    progress_percent=20,
                    message="Uploading video to X...",
                ))

            api = self._x_client["api"]
            client = self._x_client["client"]

            # Upload media using chunked upload
            loop = asyncio.get_event_loop()
            media = await loop.run_in_executor(
                self._executor,
                lambda: api.media_upload(
                    request.video_path,
                    media_category="tweet_video",
                ),
            )

            if progress_callback:
                progress_callback(PublishProgress(
                    job_id=job_id,
                    platform=SocialPlatform.X_TWITTER,
                    status=PublishStatus.PROCESSING,
                    progress_percent=70,
                    message="Processing video...",
                ))

            # Build tweet text
            tweet_text = request.title
            if request.tags:
                hashtags = " ".join(f"#{tag.replace('#', '')}" for tag in request.tags[:10])
                tweet_text += f"\n\n{hashtags}"

            # Truncate to Twitter limit
            tweet_text = tweet_text[:280]

            # Create tweet with video
            tweet = await loop.run_in_executor(
                self._executor,
                lambda: client.create_tweet(
                    text=tweet_text,
                    media_ids=[media.media_id],
                ),
            )

            tweet_id = tweet.data["id"]
            # Get username for URL
            user = client.get_me()
            username = user.data.username if user.data else "user"
            video_url = f"https://x.com/{username}/status/{tweet_id}"

            logger.info(f"Published to X: {video_url}")

            return PlatformPublishResult(
                platform=SocialPlatform.X_TWITTER,
                status=PublishStatus.PUBLISHED,
                video_id=tweet_id,
                video_url=video_url,
                published_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"X/Twitter upload failed: {e}")
            return PlatformPublishResult(
                platform=SocialPlatform.X_TWITTER,
                status=PublishStatus.FAILED,
                error_message=str(e),
            )

    async def get_platform_status(self) -> list[OAuthStatusResponse]:
        """Get connection status for all platforms."""
        statuses = []
        for platform in SocialPlatform:
            statuses.append(OAuthStatusResponse(
                platform=platform,
                connected=self._platform_status.get(platform, False),
                username=None,  # TODO: Get from cached user info
                expires_at=None,
            ))
        return statuses

    async def health_check(self) -> HealthResponse:
        """Check service health."""
        platform_status = {p.value: c for p, c in self._platform_status.items()}
        connected_count = len([c for c in self._platform_status.values() if c])

        status = "healthy" if connected_count > 0 else "degraded"

        return HealthResponse(
            status=status,
            platforms=platform_status,
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
        logger.info("Social publisher service cleaned up")
