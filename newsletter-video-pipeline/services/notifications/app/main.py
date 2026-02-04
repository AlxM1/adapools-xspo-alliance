"""
Newsletter Video Pipeline - Notifications Service.

Provides:
- Outbound webhook notifications
- Slack integration
- Discord integration
- Email notifications
- SMS notifications (optional)
- In-app notification management
"""

import asyncio
import ipaddress
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
import httpx
import uvicorn


# ============================================================
# SSRF Protection
# ============================================================

class SSRFError(Exception):
    """Raised when URL validation fails for SSRF protection."""
    pass


_BLOCKED_HOSTNAMES = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "metadata.google.internal", "169.254.169.254",
}

# Allowed webhook hosts (Slack and Discord domains)
_ALLOWED_WEBHOOK_HOSTS = {
    "hooks.slack.com",
    "discord.com",
    "discordapp.com",
}


def _validate_webhook_url(url: str, allow_any_https: bool = False) -> str:
    """
    Validate webhook URL to prevent SSRF attacks.

    For known services (Slack, Discord), we validate against their domains.
    For custom webhooks, we block internal addresses.
    """
    if not url:
        raise SSRFError("URL is required")

    parsed = urlparse(url)

    # Webhooks should use HTTPS
    if parsed.scheme.lower() != "https":
        raise SSRFError("Webhook URLs must use HTTPS")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL must contain a hostname")

    hostname_lower = hostname.lower()

    # Check if it's a known service
    if hostname_lower in _ALLOWED_WEBHOOK_HOSTS:
        return url

    # For custom webhooks, validate more strictly
    if hostname_lower in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"Access to hostname '{hostname}' is not allowed")

    # Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_private or ip.is_reserved:
            raise SSRFError("Access to internal addresses is not allowed")
    except ValueError:
        # Resolve hostname and check IPs
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
            for info in infos:
                ip_str = info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if ip.is_loopback or ip.is_private:
                        raise SSRFError("Hostname resolves to internal address")
                except ValueError:
                    continue
        except socket.gaierror:
            raise SSRFError(f"Could not resolve hostname: {hostname}")

    return url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services."""
    logger.info("Notifications Service starting...")
    yield
    logger.info("Notifications Service stopped")


app = FastAPI(
    title="Notifications Service",
    description="Multi-channel notification delivery",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - restrict in production
# Set CORS_ORIGINS env var to comma-separated list of allowed origins
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ============================================================
# Models
# ============================================================

class NotificationChannel(str, Enum):
    SLACK = "slack"
    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationEvent(str, Enum):
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    VIDEO_READY = "video.ready"
    VIDEO_PUBLISHED = "video.published"
    PUBLISH_FAILED = "publish.failed"
    CONTENT_INGESTED = "content.ingested"
    AB_TEST_COMPLETED = "ab_test.completed"
    ANALYTICS_ALERT = "analytics.alert"
    SYSTEM_ALERT = "system.alert"


class SlackConfig(BaseModel):
    """Slack webhook configuration."""
    webhook_url: str
    channel: Optional[str] = None
    username: str = "Video Pipeline Bot"
    icon_emoji: str = ":movie_camera:"


class DiscordConfig(BaseModel):
    """Discord webhook configuration."""
    webhook_url: str
    username: str = "Video Pipeline"
    avatar_url: Optional[str] = None


class EmailConfig(BaseModel):
    """Email notification configuration."""
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    from_email: str
    from_name: str = "Video Pipeline"
    use_tls: bool = True


class WebhookConfig(BaseModel):
    """Generic webhook configuration."""
    url: str
    method: str = "POST"
    headers: Optional[Dict[str, str]] = None
    secret: Optional[str] = None  # For HMAC signing


class NotificationSubscription(BaseModel):
    """User notification subscription."""
    id: str
    user_id: str
    channel: NotificationChannel
    events: List[NotificationEvent]
    config: Dict  # Channel-specific config
    is_active: bool = True
    created_at: datetime


class NotificationPayload(BaseModel):
    """Notification payload."""
    event: NotificationEvent
    title: str
    message: str
    data: Optional[Dict] = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    user_id: Optional[str] = None  # If None, send to all subscribers
    url: Optional[str] = None  # Link to relevant resource


class NotificationLog(BaseModel):
    """Notification delivery log."""
    id: str
    subscription_id: str
    event: NotificationEvent
    channel: NotificationChannel
    status: str  # sent, failed, pending
    sent_at: Optional[datetime] = None
    error: Optional[str] = None


# ============================================================
# Notification Endpoints
# ============================================================

@app.post("/notify")
async def send_notification(
    payload: NotificationPayload,
    background_tasks: BackgroundTasks,
):
    """
    Send a notification to all relevant subscribers.
    Notifications are sent asynchronously.
    """
    notification_id = str(uuid.uuid4())

    # Get subscribers for this event
    subscribers = await _get_subscribers_for_event(payload.event, payload.user_id)

    if not subscribers:
        return {
            "status": "no_subscribers",
            "notification_id": notification_id,
            "event": payload.event,
        }

    # Queue notifications for each subscriber
    for sub in subscribers:
        background_tasks.add_task(
            _deliver_notification,
            subscription=sub,
            payload=payload,
            notification_id=notification_id,
        )

    return {
        "status": "queued",
        "notification_id": notification_id,
        "event": payload.event,
        "subscriber_count": len(subscribers),
    }


@app.post("/notify/slack")
async def send_slack_notification(
    webhook_url: str,
    message: str,
    title: Optional[str] = None,
    color: str = "#36a64f",
    fields: Optional[List[Dict]] = None,
):
    """Send a direct Slack notification."""
    result = await _send_slack_message(
        webhook_url=webhook_url,
        message=message,
        title=title,
        color=color,
        fields=fields,
    )
    return result


@app.post("/notify/discord")
async def send_discord_notification(
    webhook_url: str,
    message: str,
    title: Optional[str] = None,
    color: int = 0x00ff00,
    fields: Optional[List[Dict]] = None,
):
    """Send a direct Discord notification."""
    result = await _send_discord_message(
        webhook_url=webhook_url,
        message=message,
        title=title,
        color=color,
        fields=fields,
    )
    return result


@app.post("/notify/email")
async def send_email_notification(
    to_email: EmailStr,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
):
    """Send a direct email notification."""
    result = await _send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        html_body=html_body,
    )
    return result


@app.post("/notify/webhook")
async def send_webhook_notification(
    url: str,
    payload: Dict,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
):
    """Send a generic webhook notification."""
    result = await _send_webhook(
        url=url,
        payload=payload,
        method=method,
        headers=headers,
    )
    return result


# ============================================================
# Subscription Endpoints
# ============================================================

@app.post("/subscriptions", response_model=NotificationSubscription)
async def create_subscription(
    user_id: str,
    channel: NotificationChannel,
    events: List[NotificationEvent],
    config: Dict,
):
    """Create a notification subscription."""
    subscription = NotificationSubscription(
        id=str(uuid.uuid4()),
        user_id=user_id,
        channel=channel,
        events=events,
        config=config,
        is_active=True,
        created_at=datetime.utcnow(),
    )

    # TODO: Save to database

    return subscription


@app.get("/subscriptions", response_model=List[NotificationSubscription])
async def list_subscriptions(
    user_id: Optional[str] = None,
    channel: Optional[NotificationChannel] = None,
):
    """List notification subscriptions."""
    # TODO: Fetch from database
    return []


@app.get("/subscriptions/{subscription_id}", response_model=NotificationSubscription)
async def get_subscription(subscription_id: str):
    """Get subscription details."""
    # TODO: Fetch from database
    raise HTTPException(status_code=404, detail="Subscription not found")


@app.put("/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    events: Optional[List[NotificationEvent]] = None,
    config: Optional[Dict] = None,
    is_active: Optional[bool] = None,
):
    """Update a subscription."""
    # TODO: Update in database
    return {"status": "updated", "subscription_id": subscription_id}


@app.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    """Delete a subscription."""
    # TODO: Delete from database
    return {"status": "deleted", "subscription_id": subscription_id}


# ============================================================
# Notification Log Endpoints
# ============================================================

@app.get("/logs", response_model=List[NotificationLog])
async def list_notification_logs(
    user_id: Optional[str] = None,
    event: Optional[NotificationEvent] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """List notification delivery logs."""
    # TODO: Fetch from database
    return []


@app.post("/logs/{log_id}/retry")
async def retry_notification(log_id: str, background_tasks: BackgroundTasks):
    """Retry a failed notification."""
    # TODO: Implement
    return {"status": "retrying", "log_id": log_id}


# ============================================================
# Template Endpoints
# ============================================================

@app.get("/templates")
async def list_notification_templates():
    """List notification templates for each event type."""
    templates = {
        NotificationEvent.PIPELINE_STARTED: {
            "title": "Pipeline Started",
            "message": "Your video pipeline for '{title}' has started processing.",
            "slack_color": "#2196F3",
            "discord_color": 0x2196F3,
        },
        NotificationEvent.PIPELINE_COMPLETED: {
            "title": "Pipeline Completed",
            "message": "Your video for '{title}' is ready! {video_count} videos generated.",
            "slack_color": "#4CAF50",
            "discord_color": 0x4CAF50,
        },
        NotificationEvent.PIPELINE_FAILED: {
            "title": "Pipeline Failed",
            "message": "Pipeline for '{title}' failed: {error}",
            "slack_color": "#F44336",
            "discord_color": 0xF44336,
        },
        NotificationEvent.VIDEO_PUBLISHED: {
            "title": "Video Published",
            "message": "'{title}' has been published to {platform}!",
            "slack_color": "#9C27B0",
            "discord_color": 0x9C27B0,
        },
    }
    return templates


# ============================================================
# Test Endpoints
# ============================================================

@app.post("/test/slack")
async def test_slack_webhook(webhook_url: str):
    """Test Slack webhook configuration."""
    result = await _send_slack_message(
        webhook_url=webhook_url,
        message="This is a test notification from Video Pipeline.",
        title="Test Notification",
        color="#36a64f",
    )
    return result


@app.post("/test/discord")
async def test_discord_webhook(webhook_url: str):
    """Test Discord webhook configuration."""
    result = await _send_discord_message(
        webhook_url=webhook_url,
        message="This is a test notification from Video Pipeline.",
        title="Test Notification",
        color=0x00ff00,
    )
    return result


# ============================================================
# Helper Functions
# ============================================================

async def _get_subscribers_for_event(
    event: NotificationEvent,
    user_id: Optional[str],
) -> List[NotificationSubscription]:
    """Get all active subscribers for an event."""
    # TODO: Implement database query
    return []


async def _deliver_notification(
    subscription: NotificationSubscription,
    payload: NotificationPayload,
    notification_id: str,
):
    """Deliver notification to a subscriber."""
    try:
        if subscription.channel == NotificationChannel.SLACK:
            await _send_slack_message(
                webhook_url=subscription.config.get("webhook_url"),
                message=payload.message,
                title=payload.title,
                fields=[{"name": k, "value": str(v)} for k, v in (payload.data or {}).items()],
            )
        elif subscription.channel == NotificationChannel.DISCORD:
            await _send_discord_message(
                webhook_url=subscription.config.get("webhook_url"),
                message=payload.message,
                title=payload.title,
                fields=[{"name": k, "value": str(v)} for k, v in (payload.data or {}).items()],
            )
        elif subscription.channel == NotificationChannel.EMAIL:
            await _send_email(
                to_email=subscription.config.get("email"),
                subject=payload.title,
                body=payload.message,
            )
        elif subscription.channel == NotificationChannel.WEBHOOK:
            await _send_webhook(
                url=subscription.config.get("url"),
                payload={
                    "event": payload.event,
                    "title": payload.title,
                    "message": payload.message,
                    "data": payload.data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        # Log success
        logger.info(f"Notification delivered: {notification_id} to {subscription.id}")

    except Exception as e:
        logger.error(f"Notification failed: {notification_id} to {subscription.id}: {e}")


async def _send_slack_message(
    webhook_url: str,
    message: str,
    title: Optional[str] = None,
    color: str = "#36a64f",
    fields: Optional[List[Dict]] = None,
) -> Dict:
    """Send Slack webhook message."""
    # Validate URL to prevent SSRF
    try:
        _validate_webhook_url(webhook_url)
    except SSRFError as e:
        return {"status": "failed", "error": f"Invalid webhook URL: {e}"}

    payload = {
        "attachments": [
            {
                "color": color,
                "title": title,
                "text": message,
                "fields": [
                    {"title": f["name"], "value": f["value"], "short": True}
                    for f in (fields or [])
                ],
                "footer": "Video Pipeline",
                "ts": int(datetime.utcnow().timestamp()),
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(webhook_url, json=payload)

        if response.status_code == 200:
            return {"status": "sent", "channel": "slack"}
        else:
            return {"status": "failed", "error": response.text}


async def _send_discord_message(
    webhook_url: str,
    message: str,
    title: Optional[str] = None,
    color: int = 0x00ff00,
    fields: Optional[List[Dict]] = None,
) -> Dict:
    """Send Discord webhook message."""
    # Validate URL to prevent SSRF
    try:
        _validate_webhook_url(webhook_url)
    except SSRFError as e:
        return {"status": "failed", "error": f"Invalid webhook URL: {e}"}

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Video Pipeline"},
    }

    if fields:
        embed["fields"] = [
            {"name": f["name"], "value": f["value"], "inline": True}
            for f in fields
        ]

    payload = {"embeds": [embed]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(webhook_url, json=payload)

        if response.status_code in (200, 204):
            return {"status": "sent", "channel": "discord"}
        else:
            return {"status": "failed", "error": response.text}


async def _send_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
) -> Dict:
    """Send email notification."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM", "noreply@videopipeline.local")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain"))

        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_email, msg.as_string())

        return {"status": "sent", "channel": "email"}

    except Exception as e:
        return {"status": "failed", "error": str(e)}


async def _send_webhook(
    url: str,
    payload: Dict,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
) -> Dict:
    """Send generic webhook."""
    # Validate URL to prevent SSRF
    try:
        _validate_webhook_url(url)
    except SSRFError as e:
        return {"status": "failed", "error": f"Invalid webhook URL: {e}"}

    async with httpx.AsyncClient(timeout=30) as client:
        if method.upper() == "POST":
            response = await client.post(url, json=payload, headers=headers)
        elif method.upper() == "PUT":
            response = await client.put(url, json=payload, headers=headers)
        else:
            return {"status": "failed", "error": f"Unsupported method: {method}"}

        if response.status_code < 400:
            return {"status": "sent", "channel": "webhook", "response_code": response.status_code}
        else:
            return {"status": "failed", "error": response.text}


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "notifications",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5015)
