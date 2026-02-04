"""
Newsletter Video Pipeline - Content Ingestion Service.

Automatically ingests newsletters from multiple sources:
- RSS/Atom feeds
- Email (IMAP)
- Webhooks (Zapier, Make, n8n, custom)
- Manual API submissions
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
import uvicorn

from .ingestion import RSSIngester, EmailIngester, WebhookHandler
from .content_scorer import ContentScorer
from .queue import ContentQueue

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
rss_ingester: Optional[RSSIngester] = None
email_ingester: Optional[EmailIngester] = None
content_queue: Optional[ContentQueue] = None
content_scorer: Optional[ContentScorer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    global rss_ingester, email_ingester, content_queue, content_scorer

    logger.info("Initializing Content Ingestion Service...")

    content_queue = ContentQueue()
    content_scorer = ContentScorer()
    rss_ingester = RSSIngester(content_queue, content_scorer)
    email_ingester = EmailIngester(content_queue, content_scorer)

    # Start background polling tasks
    asyncio.create_task(rss_ingester.start_polling())
    asyncio.create_task(email_ingester.start_polling())

    logger.info("Content Ingestion Service ready")
    yield

    # Cleanup
    await rss_ingester.stop()
    await email_ingester.stop()
    logger.info("Content Ingestion Service stopped")


app = FastAPI(
    title="Content Ingestion Service",
    description="Automatically ingest newsletters from RSS, Email, and Webhooks",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Models
# ============================================================

class RSSFeedCreate(BaseModel):
    """Create a new RSS feed subscription."""
    url: HttpUrl
    name: str
    check_interval_minutes: int = Field(default=60, ge=5, le=1440)
    auto_process: bool = True
    filters: Optional[dict] = None  # Title/content filters


class RSSFeed(RSSFeedCreate):
    """RSS feed with metadata."""
    id: str
    created_at: datetime
    last_checked: Optional[datetime] = None
    items_ingested: int = 0
    is_active: bool = True


class EmailSourceCreate(BaseModel):
    """Configure email ingestion source."""
    name: str
    imap_server: str
    imap_port: int = 993
    username: str
    password: str
    folder: str = "INBOX"
    sender_filter: Optional[str] = None  # Filter by sender
    subject_filter: Optional[str] = None  # Filter by subject regex
    check_interval_minutes: int = Field(default=15, ge=5, le=1440)
    auto_process: bool = True
    mark_as_read: bool = True


class EmailSource(BaseModel):
    """Email source with metadata."""
    id: str
    name: str
    imap_server: str
    folder: str
    is_active: bool = True
    last_checked: Optional[datetime] = None
    emails_ingested: int = 0


class WebhookPayload(BaseModel):
    """Generic webhook payload for content ingestion."""
    title: str
    content: str
    source: str = "webhook"
    metadata: Optional[dict] = None
    auto_process: bool = True
    priority: int = Field(default=5, ge=1, le=10)


class ContentItem(BaseModel):
    """Ingested content item."""
    id: str
    title: str
    content: str
    source_type: str  # rss, email, webhook, api
    source_id: str
    ingested_at: datetime
    score: float  # Engagement potential score
    segments: list[dict]  # Extracted segments for shorts
    status: str  # pending, processing, completed, failed
    pipeline_job_id: Optional[str] = None


class ContentSegment(BaseModel):
    """Extracted content segment for short-form video."""
    id: str
    content_id: str
    text: str
    segment_type: str  # hook, quote, statistic, insight, cta
    score: float
    word_count: int
    estimated_duration_sec: int


# ============================================================
# RSS Feed Endpoints
# ============================================================

@app.post("/rss/feeds", response_model=RSSFeed)
async def create_rss_feed(feed: RSSFeedCreate):
    """Subscribe to a new RSS feed."""
    return await rss_ingester.add_feed(feed)


@app.get("/rss/feeds", response_model=list[RSSFeed])
async def list_rss_feeds():
    """List all RSS feed subscriptions."""
    return await rss_ingester.list_feeds()


@app.get("/rss/feeds/{feed_id}", response_model=RSSFeed)
async def get_rss_feed(feed_id: str):
    """Get RSS feed details."""
    feed = await rss_ingester.get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed


@app.delete("/rss/feeds/{feed_id}")
async def delete_rss_feed(feed_id: str):
    """Unsubscribe from RSS feed."""
    success = await rss_ingester.remove_feed(feed_id)
    if not success:
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"status": "deleted"}


@app.post("/rss/feeds/{feed_id}/check")
async def check_rss_feed(feed_id: str, background_tasks: BackgroundTasks):
    """Manually trigger feed check."""
    feed = await rss_ingester.get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    background_tasks.add_task(rss_ingester.check_feed, feed_id)
    return {"status": "checking", "feed_id": feed_id}


# ============================================================
# Email Ingestion Endpoints
# ============================================================

@app.post("/email/sources", response_model=EmailSource)
async def create_email_source(source: EmailSourceCreate):
    """Configure email ingestion source."""
    return await email_ingester.add_source(source)


@app.get("/email/sources", response_model=list[EmailSource])
async def list_email_sources():
    """List all email sources."""
    return await email_ingester.list_sources()


@app.delete("/email/sources/{source_id}")
async def delete_email_source(source_id: str):
    """Remove email source."""
    success = await email_ingester.remove_source(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "deleted"}


@app.post("/email/sources/{source_id}/check")
async def check_email_source(source_id: str, background_tasks: BackgroundTasks):
    """Manually check email source."""
    source = await email_ingester.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    background_tasks.add_task(email_ingester.check_source, source_id)
    return {"status": "checking", "source_id": source_id}


# ============================================================
# Webhook Endpoints
# ============================================================

@app.post("/webhooks/ingest")
async def webhook_ingest(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Generic webhook endpoint for content ingestion.
    Compatible with Zapier, Make, n8n, and custom integrations.
    """
    # Verify webhook secret if configured
    handler = WebhookHandler(content_queue, content_scorer)

    content_item = await handler.process_webhook(payload)

    if payload.auto_process:
        background_tasks.add_task(
            content_queue.trigger_pipeline,
            content_item.id
        )

    return {
        "status": "ingested",
        "content_id": content_item.id,
        "score": content_item.score,
        "segments_found": len(content_item.segments),
    }


@app.post("/webhooks/zapier")
async def zapier_webhook(
    background_tasks: BackgroundTasks,
    title: str,
    content: str,
    source: str = "zapier",
):
    """Zapier-specific webhook with simple query params."""
    payload = WebhookPayload(title=title, content=content, source=source)
    handler = WebhookHandler(content_queue, content_scorer)
    content_item = await handler.process_webhook(payload)

    background_tasks.add_task(content_queue.trigger_pipeline, content_item.id)

    return {"content_id": content_item.id, "status": "processing"}


@app.post("/webhooks/n8n")
async def n8n_webhook(
    background_tasks: BackgroundTasks,
    data: dict,
):
    """n8n-specific webhook handler."""
    title = data.get("title", data.get("subject", "Untitled"))
    content = data.get("content", data.get("body", data.get("text", "")))

    payload = WebhookPayload(
        title=title,
        content=content,
        source="n8n",
        metadata=data,
    )

    handler = WebhookHandler(content_queue, content_scorer)
    content_item = await handler.process_webhook(payload)

    background_tasks.add_task(content_queue.trigger_pipeline, content_item.id)

    return {"content_id": content_item.id, "status": "processing"}


# ============================================================
# Content Queue Endpoints
# ============================================================

@app.get("/content", response_model=list[ContentItem])
async def list_content(
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List ingested content items."""
    return await content_queue.list_items(
        status=status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )


@app.get("/content/{content_id}", response_model=ContentItem)
async def get_content(content_id: str):
    """Get content item details."""
    item = await content_queue.get_item(content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")
    return item


@app.get("/content/{content_id}/segments", response_model=list[ContentSegment])
async def get_content_segments(content_id: str):
    """Get extracted segments for a content item."""
    item = await content_queue.get_item(content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")
    return item.segments


@app.post("/content/{content_id}/process")
async def process_content(content_id: str, background_tasks: BackgroundTasks):
    """Trigger pipeline processing for content item."""
    item = await content_queue.get_item(content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    background_tasks.add_task(content_queue.trigger_pipeline, content_id)
    return {"status": "processing", "content_id": content_id}


@app.delete("/content/{content_id}")
async def delete_content(content_id: str):
    """Delete content item."""
    success = await content_queue.delete_item(content_id)
    if not success:
        raise HTTPException(status_code=404, detail="Content not found")
    return {"status": "deleted"}


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "content-ingestion",
        "rss_feeds_active": await rss_ingester.get_active_count() if rss_ingester else 0,
        "email_sources_active": await email_ingester.get_active_count() if email_ingester else 0,
        "queue_size": await content_queue.get_queue_size() if content_queue else 0,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5010)
