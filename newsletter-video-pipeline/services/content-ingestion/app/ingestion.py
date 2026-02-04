"""
Content ingestion handlers for RSS, Email, and Webhooks.
"""

import asyncio
import hashlib
import imaplib
import email
import re
import uuid
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional
from html import unescape

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from .content_scorer import ContentScorer
from .queue import ContentQueue, ContentItem


class RSSIngester:
    """RSS/Atom feed ingester with automatic polling."""

    def __init__(self, queue: ContentQueue, scorer: ContentScorer):
        self.queue = queue
        self.scorer = scorer
        self.feeds: dict[str, dict] = {}
        self.seen_items: set[str] = set()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    async def add_feed(self, feed_data) -> dict:
        """Add a new RSS feed subscription."""
        feed_id = str(uuid.uuid4())

        feed = {
            "id": feed_id,
            "url": str(feed_data.url),
            "name": feed_data.name,
            "check_interval_minutes": feed_data.check_interval_minutes,
            "auto_process": feed_data.auto_process,
            "filters": feed_data.filters or {},
            "created_at": datetime.utcnow(),
            "last_checked": None,
            "items_ingested": 0,
            "is_active": True,
        }

        self.feeds[feed_id] = feed

        # Initial check
        await self.check_feed(feed_id)

        return feed

    async def list_feeds(self) -> list[dict]:
        """List all feeds."""
        return list(self.feeds.values())

    async def get_feed(self, feed_id: str) -> Optional[dict]:
        """Get feed by ID."""
        return self.feeds.get(feed_id)

    async def remove_feed(self, feed_id: str) -> bool:
        """Remove a feed subscription."""
        if feed_id in self.feeds:
            del self.feeds[feed_id]
            return True
        return False

    async def get_active_count(self) -> int:
        """Get count of active feeds."""
        return sum(1 for f in self.feeds.values() if f["is_active"])

    async def check_feed(self, feed_id: str):
        """Check a feed for new items."""
        feed = self.feeds.get(feed_id)
        if not feed or not feed["is_active"]:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed["url"], timeout=30) as response:
                    content = await response.text()

            parsed = feedparser.parse(content)

            for entry in parsed.entries:
                # Generate unique ID for item
                item_id = hashlib.md5(
                    (entry.get("id", entry.get("link", entry.get("title", "")))).encode()
                ).hexdigest()

                if item_id in self.seen_items:
                    continue

                self.seen_items.add(item_id)

                # Extract content
                title = entry.get("title", "Untitled")
                content = self._extract_content(entry)

                # Apply filters if configured
                if feed["filters"]:
                    if not self._passes_filters(title, content, feed["filters"]):
                        continue

                # Score and segment the content
                score = await self.scorer.score_content(title, content)
                segments = await self.scorer.extract_segments(content)

                # Create content item
                content_item = ContentItem(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=content,
                    source_type="rss",
                    source_id=feed_id,
                    ingested_at=datetime.utcnow(),
                    score=score,
                    segments=segments,
                    status="pending",
                )

                await self.queue.add_item(content_item)
                feed["items_ingested"] += 1

                # Auto-process if enabled
                if feed["auto_process"]:
                    await self.queue.trigger_pipeline(content_item.id)

            feed["last_checked"] = datetime.utcnow()

        except Exception as e:
            print(f"Error checking feed {feed_id}: {e}")

    def _extract_content(self, entry) -> str:
        """Extract clean text content from feed entry."""
        # Try different content fields
        content = ""

        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary
        elif hasattr(entry, "description"):
            content = entry.description

        # Clean HTML
        soup = BeautifulSoup(content, "html.parser")

        # Remove scripts and styles
        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)

        return unescape(text)

    def _passes_filters(self, title: str, content: str, filters: dict) -> bool:
        """Check if content passes configured filters."""
        if "title_contains" in filters:
            if filters["title_contains"].lower() not in title.lower():
                return False

        if "title_regex" in filters:
            if not re.search(filters["title_regex"], title, re.IGNORECASE):
                return False

        if "content_contains" in filters:
            if filters["content_contains"].lower() not in content.lower():
                return False

        if "min_length" in filters:
            if len(content) < filters["min_length"]:
                return False

        return True

    async def start_polling(self):
        """Start background polling of feeds."""
        self._running = True

        while self._running:
            for feed_id, feed in list(self.feeds.items()):
                if not feed["is_active"]:
                    continue

                # Check if it's time to poll
                if feed["last_checked"]:
                    next_check = feed["last_checked"] + timedelta(
                        minutes=feed["check_interval_minutes"]
                    )
                    if datetime.utcnow() < next_check:
                        continue

                await self.check_feed(feed_id)

            # Sleep before next round
            await asyncio.sleep(60)

    async def stop(self):
        """Stop polling."""
        self._running = False


class EmailIngester:
    """Email ingestion via IMAP."""

    def __init__(self, queue: ContentQueue, scorer: ContentScorer):
        self.queue = queue
        self.scorer = scorer
        self.sources: dict[str, dict] = {}
        self.seen_emails: set[str] = set()
        self._running = False

    async def add_source(self, source_data) -> dict:
        """Add email source configuration."""
        source_id = str(uuid.uuid4())

        source = {
            "id": source_id,
            "name": source_data.name,
            "imap_server": source_data.imap_server,
            "imap_port": source_data.imap_port,
            "username": source_data.username,
            "password": source_data.password,
            "folder": source_data.folder,
            "sender_filter": source_data.sender_filter,
            "subject_filter": source_data.subject_filter,
            "check_interval_minutes": source_data.check_interval_minutes,
            "auto_process": source_data.auto_process,
            "mark_as_read": source_data.mark_as_read,
            "is_active": True,
            "last_checked": None,
            "emails_ingested": 0,
        }

        self.sources[source_id] = source

        # Initial check
        await self.check_source(source_id)

        return {
            "id": source_id,
            "name": source_data.name,
            "imap_server": source_data.imap_server,
            "folder": source_data.folder,
            "is_active": True,
            "last_checked": None,
            "emails_ingested": 0,
        }

    async def list_sources(self) -> list[dict]:
        """List email sources (without credentials)."""
        return [
            {
                "id": s["id"],
                "name": s["name"],
                "imap_server": s["imap_server"],
                "folder": s["folder"],
                "is_active": s["is_active"],
                "last_checked": s["last_checked"],
                "emails_ingested": s["emails_ingested"],
            }
            for s in self.sources.values()
        ]

    async def get_source(self, source_id: str) -> Optional[dict]:
        """Get source by ID."""
        return self.sources.get(source_id)

    async def remove_source(self, source_id: str) -> bool:
        """Remove email source."""
        if source_id in self.sources:
            del self.sources[source_id]
            return True
        return False

    async def get_active_count(self) -> int:
        """Get count of active sources."""
        return sum(1 for s in self.sources.values() if s["is_active"])

    async def check_source(self, source_id: str):
        """Check email source for new messages."""
        source = self.sources.get(source_id)
        if not source or not source["is_active"]:
            return

        try:
            # Run IMAP operations in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._check_imap,
                source,
            )

            source["last_checked"] = datetime.utcnow()

        except Exception as e:
            print(f"Error checking email source {source_id}: {e}")

    def _check_imap(self, source: dict):
        """Synchronous IMAP checking (run in thread pool)."""
        try:
            # Connect to IMAP
            mail = imaplib.IMAP4_SSL(source["imap_server"], source["imap_port"])
            mail.login(source["username"], source["password"])
            mail.select(source["folder"])

            # Search for unread messages
            search_criteria = "UNSEEN"

            if source["sender_filter"]:
                search_criteria = f'(UNSEEN FROM "{source["sender_filter"]}")'

            _, message_ids = mail.search(None, search_criteria)

            for msg_id in message_ids[0].split():
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)

                # Generate unique ID
                msg_hash = hashlib.md5(
                    f"{msg['Message-ID']}{msg['Date']}".encode()
                ).hexdigest()

                if msg_hash in self.seen_emails:
                    continue

                self.seen_emails.add(msg_hash)

                # Decode subject
                subject = self._decode_header(msg["Subject"])

                # Apply subject filter
                if source["subject_filter"]:
                    if not re.search(source["subject_filter"], subject, re.IGNORECASE):
                        continue

                # Extract body
                body = self._extract_email_body(msg)

                # Score and segment
                score = asyncio.run(self.scorer.score_content(subject, body))
                segments = asyncio.run(self.scorer.extract_segments(body))

                # Create content item
                content_item = ContentItem(
                    id=str(uuid.uuid4()),
                    title=subject,
                    content=body,
                    source_type="email",
                    source_id=source["id"],
                    ingested_at=datetime.utcnow(),
                    score=score,
                    segments=segments,
                    status="pending",
                )

                asyncio.run(self.queue.add_item(content_item))
                source["emails_ingested"] += 1

                # Auto-process
                if source["auto_process"]:
                    asyncio.run(self.queue.trigger_pipeline(content_item.id))

                # Mark as read
                if source["mark_as_read"]:
                    mail.store(msg_id, "+FLAGS", "\\Seen")

            mail.close()
            mail.logout()

        except Exception as e:
            print(f"IMAP error: {e}")

    def _decode_header(self, header) -> str:
        """Decode email header."""
        if not header:
            return ""

        decoded = decode_header(header)
        result = ""

        for part, encoding in decoded:
            if isinstance(part, bytes):
                result += part.decode(encoding or "utf-8", errors="replace")
            else:
                result += part

        return result

    def _extract_email_body(self, msg) -> str:
        """Extract text body from email message."""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace"
                    )
                    break
                elif content_type == "text/html" and not body:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace"
                    )
                    soup = BeautifulSoup(html, "html.parser")
                    body = soup.get_text(separator="\n")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(
                    msg.get_content_charset() or "utf-8",
                    errors="replace"
                )

        return body.strip()

    async def start_polling(self):
        """Start background polling."""
        self._running = True

        while self._running:
            for source_id, source in list(self.sources.items()):
                if not source["is_active"]:
                    continue

                if source["last_checked"]:
                    next_check = source["last_checked"] + timedelta(
                        minutes=source["check_interval_minutes"]
                    )
                    if datetime.utcnow() < next_check:
                        continue

                await self.check_source(source_id)

            await asyncio.sleep(60)

    async def stop(self):
        """Stop polling."""
        self._running = False


class WebhookHandler:
    """Handle incoming webhooks."""

    def __init__(self, queue: ContentQueue, scorer: ContentScorer):
        self.queue = queue
        self.scorer = scorer

    async def process_webhook(self, payload) -> ContentItem:
        """Process incoming webhook payload."""
        # Score the content
        score = await self.scorer.score_content(payload.title, payload.content)
        segments = await self.scorer.extract_segments(payload.content)

        # Create content item
        content_item = ContentItem(
            id=str(uuid.uuid4()),
            title=payload.title,
            content=payload.content,
            source_type="webhook",
            source_id=payload.source,
            ingested_at=datetime.utcnow(),
            score=score,
            segments=segments,
            status="pending",
        )

        await self.queue.add_item(content_item)

        return content_item
