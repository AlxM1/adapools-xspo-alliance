"""
FastAPI application for Social Publisher Service.

This runs on the Linux VM and exposes REST API for:
- Multi-platform video publishing
- OAuth authentication flow
- Publishing status tracking
"""

import os
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from .service import SocialPublisherService
from .models import (
    PublishRequest,
    PublishResponse,
    OAuthStatusResponse,
    HealthResponse,
    SocialPlatform,
)

# Global service instance
social_service: Optional[SocialPublisherService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global social_service

    # Startup
    logger.info("Starting Social Publisher Service...")

    social_service = SocialPublisherService(
        credentials_dir=os.getenv("SOCIAL_CREDENTIALS_DIR", "/data/credentials"),
        temp_dir=os.getenv("SOCIAL_TEMP_DIR", "/tmp/social_publisher"),
    )

    await social_service.initialize()
    logger.info("Social Publisher Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Social Publisher Service...")
    if social_service:
        await social_service.cleanup()
    logger.info("Social Publisher Service stopped")


app = FastAPI(
    title="Social Publisher Service",
    description="Multi-platform video publishing to YouTube, TikTok, Instagram, and X",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and platform connections."""
    if not social_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await social_service.health_check()


@app.get("/platforms", response_model=list[OAuthStatusResponse])
async def get_platforms():
    """Get connection status for all platforms."""
    if not social_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await social_service.get_platform_status()


@app.post("/publish", response_model=PublishResponse)
async def publish_video(request: PublishRequest):
    """
    Publish a video to specified platform(s).

    The video file must already exist on the server.
    """
    if not social_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await social_service.publish(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Publishing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Publishing failed: {e}")


# ============================================================
# OAuth Authentication Endpoints
# ============================================================

@app.get("/auth/youtube")
async def auth_youtube(request: Request):
    """Start YouTube OAuth flow."""
    from google_auth_oauthlib.flow import Flow

    client_secrets_file = os.getenv(
        "SOCIAL_YOUTUBE_CLIENT_SECRETS_FILE",
        "/configs/youtube_client_secrets.json"
    )

    if not Path(client_secrets_file).exists():
        raise HTTPException(
            status_code=400,
            detail="YouTube client secrets not configured. "
                   "Please add youtube_client_secrets.json"
        )

    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
        redirect_uri=str(request.url_for("auth_youtube_callback")),
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    return RedirectResponse(auth_url)


@app.get("/auth/youtube/callback")
async def auth_youtube_callback(code: str, request: Request):
    """YouTube OAuth callback."""
    from google_auth_oauthlib.flow import Flow

    client_secrets_file = os.getenv(
        "SOCIAL_YOUTUBE_CLIENT_SECRETS_FILE",
        "/configs/youtube_client_secrets.json"
    )

    flow = Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
        redirect_uri=str(request.url_for("auth_youtube_callback")),
    )

    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Save credentials
    creds_dir = Path(os.getenv("SOCIAL_CREDENTIALS_DIR", "/data/credentials"))
    creds_dir.mkdir(parents=True, exist_ok=True)

    creds_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

    with open(creds_dir / "youtube_credentials.json", "w") as f:
        json.dump(creds_data, f, indent=2)

    # Reinitialize service
    await social_service._init_youtube()

    return {"message": "YouTube connected successfully", "success": True}


@app.get("/auth/tiktok")
async def auth_tiktok(request: Request):
    """Start TikTok OAuth flow."""
    client_key = os.getenv("SOCIAL_TIKTOK_CLIENT_KEY")
    if not client_key:
        raise HTTPException(
            status_code=400,
            detail="TikTok client key not configured"
        )

    redirect_uri = str(request.url_for("auth_tiktok_callback"))

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={client_key}"
        f"&scope=user.info.basic,video.upload,video.publish"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
    )

    return RedirectResponse(auth_url)


@app.get("/auth/tiktok/callback")
async def auth_tiktok_callback(code: str):
    """TikTok OAuth callback."""
    import httpx

    client_key = os.getenv("SOCIAL_TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("SOCIAL_TIKTOK_CLIENT_SECRET")
    redirect_uri = os.getenv("SOCIAL_TIKTOK_REDIRECT_URI")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

        data = response.json()

        if "access_token" not in data:
            raise HTTPException(status_code=400, detail=f"TikTok auth failed: {data}")

        # Save credentials
        creds_dir = Path(os.getenv("SOCIAL_CREDENTIALS_DIR", "/data/credentials"))
        creds_dir.mkdir(parents=True, exist_ok=True)

        with open(creds_dir / "tiktok_credentials.json", "w") as f:
            json.dump(data, f, indent=2)

        # Reinitialize service
        await social_service._init_tiktok()

        return {"message": "TikTok connected successfully", "success": True}


@app.post("/auth/instagram")
async def auth_instagram(username: str, password: str):
    """Connect Instagram account (direct login)."""
    if not social_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        from instagrapi import Client

        client = Client()
        client.login(username, password)

        # Save session
        creds_dir = Path(os.getenv("SOCIAL_CREDENTIALS_DIR", "/data/credentials"))
        creds_dir.mkdir(parents=True, exist_ok=True)

        client.dump_settings(creds_dir / "instagram_session.json")

        # Save credentials for re-login
        with open(creds_dir / "instagram_credentials.json", "w") as f:
            json.dump({"username": username, "password": password}, f)

        # Update service
        social_service._instagram_client = client
        social_service._platform_status[SocialPlatform.INSTAGRAM] = True

        return {"message": "Instagram connected successfully", "success": True}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Instagram login failed: {e}")


@app.post("/auth/x")
async def auth_x(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    bearer_token: str,
):
    """Connect X/Twitter account with API credentials."""
    if not social_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        # Save credentials
        creds_dir = Path(os.getenv("SOCIAL_CREDENTIALS_DIR", "/data/credentials"))
        creds_dir.mkdir(parents=True, exist_ok=True)

        creds_data = {
            "api_key": api_key,
            "api_secret": api_secret,
            "access_token": access_token,
            "access_token_secret": access_token_secret,
            "bearer_token": bearer_token,
        }

        with open(creds_dir / "x_credentials.json", "w") as f:
            json.dump(creds_data, f, indent=2)

        # Reinitialize
        await social_service._init_x_twitter()

        return {"message": "X/Twitter connected successfully", "success": True}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"X/Twitter auth failed: {e}")


def main():
    """Run the social publisher service."""
    uvicorn.run(
        "services.social_publisher.app:app",
        host=os.getenv("SOCIAL_HOST", "0.0.0.0"),
        port=int(os.getenv("SOCIAL_PORT", "5006")),
        reload=os.getenv("SOCIAL_RELOAD", "false").lower() == "true",
        workers=int(os.getenv("SOCIAL_WORKERS", "2")),
    )


if __name__ == "__main__":
    main()
