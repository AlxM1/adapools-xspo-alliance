"""
Content queue management for ingested items.
"""

import os
import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
import json

import httpx
import redis.asyncio as redis


@dataclass
class ContentItem:
    """Ingested content item."""
    id: str
    title: str
    content: str
    source_type: str
    source_id: str
    ingested_at: datetime
    score: float
    segments: list[dict]
    status: str = "pending"
    pipeline_job_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        data["ingested_at"] = self.ingested_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ContentItem":
        """Create from dictionary."""
        data["ingested_at"] = datetime.fromisoformat(data["ingested_at"])
        return cls(**data)


class ContentQueue:
    """Manages queue of ingested content items."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.api_gateway_url = os.getenv("API_GATEWAY_URL", "http://localhost:8000")
        self._redis: Optional[redis.Redis] = None
        self._items: dict[str, ContentItem] = {}  # In-memory fallback

    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if self._redis is None:
            try:
                self._redis = redis.from_url(self.redis_url)
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    async def add_item(self, item: ContentItem):
        """Add content item to queue."""
        r = await self._get_redis()

        if r:
            # Store in Redis
            await r.hset(
                "content:items",
                item.id,
                json.dumps(item.to_dict())
            )
            # Add to sorted set by score for priority queue
            await r.zadd("content:queue", {item.id: item.score})
        else:
            # Fallback to in-memory
            self._items[item.id] = item

    async def get_item(self, item_id: str) -> Optional[ContentItem]:
        """Get content item by ID."""
        r = await self._get_redis()

        if r:
            data = await r.hget("content:items", item_id)
            if data:
                return ContentItem.from_dict(json.loads(data))
        else:
            return self._items.get(item_id)

        return None

    async def update_item(self, item: ContentItem):
        """Update content item."""
        r = await self._get_redis()

        if r:
            await r.hset(
                "content:items",
                item.id,
                json.dumps(item.to_dict())
            )
        else:
            self._items[item.id] = item

    async def delete_item(self, item_id: str) -> bool:
        """Delete content item."""
        r = await self._get_redis()

        if r:
            result = await r.hdel("content:items", item_id)
            await r.zrem("content:queue", item_id)
            return result > 0
        else:
            if item_id in self._items:
                del self._items[item_id]
                return True

        return False

    async def list_items(
        self,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentItem]:
        """List content items with optional filters."""
        r = await self._get_redis()
        items = []

        if r:
            # Get all items from Redis
            all_items = await r.hgetall("content:items")
            for data in all_items.values():
                item = ContentItem.from_dict(json.loads(data))
                items.append(item)
        else:
            items = list(self._items.values())

        # Apply filters
        if status:
            items = [i for i in items if i.status == status]
        if source_type:
            items = [i for i in items if i.source_type == source_type]

        # Sort by score descending
        items.sort(key=lambda x: x.score, reverse=True)

        # Apply pagination
        return items[offset:offset + limit]

    async def get_queue_size(self) -> int:
        """Get number of items in queue."""
        r = await self._get_redis()

        if r:
            return await r.hlen("content:items")
        else:
            return len(self._items)

    async def trigger_pipeline(self, content_id: str):
        """Trigger video pipeline for content item."""
        item = await self.get_item(content_id)
        if not item:
            return

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_gateway_url}/api/v1/pipelines",
                    json={
                        "newsletter_title": item.title,
                        "newsletter_content": item.content,
                        "source_type": item.source_type,
                        "source_id": item.source_id,
                        "content_score": item.score,
                        "segments": item.segments,
                        "generate_long_form": True,
                        "generate_shorts": True,
                        "shorts_count": min(len(item.segments), 5),
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    item.pipeline_job_id = result.get("id")
                    item.status = "processing"
                    await self.update_item(item)
                else:
                    print(f"Pipeline trigger failed: {response.status_code}")
                    item.status = "failed"
                    await self.update_item(item)

        except Exception as e:
            print(f"Error triggering pipeline: {e}")
            item.status = "failed"
            await self.update_item(item)


class PriorityQueue:
    """Priority queue for content processing based on scores."""

    def __init__(self, queue: ContentQueue):
        self.queue = queue

    async def get_next(self) -> Optional[ContentItem]:
        """Get next highest-priority content item."""
        r = await self.queue._get_redis()

        if r:
            # Get highest scored item
            result = await r.zrevrange("content:queue", 0, 0)
            if result:
                item_id = result[0]
                return await self.queue.get_item(item_id)
        else:
            # In-memory fallback
            pending = [
                i for i in self.queue._items.values()
                if i.status == "pending"
            ]
            if pending:
                return max(pending, key=lambda x: x.score)

        return None

    async def mark_processing(self, item_id: str):
        """Mark item as being processed."""
        item = await self.queue.get_item(item_id)
        if item:
            item.status = "processing"
            await self.queue.update_item(item)

            r = await self.queue._get_redis()
            if r:
                await r.zrem("content:queue", item_id)

    async def mark_completed(self, item_id: str, pipeline_job_id: str):
        """Mark item as completed."""
        item = await self.queue.get_item(item_id)
        if item:
            item.status = "completed"
            item.pipeline_job_id = pipeline_job_id
            await self.queue.update_item(item)

    async def mark_failed(self, item_id: str, error: str = None):
        """Mark item as failed."""
        item = await self.queue.get_item(item_id)
        if item:
            item.status = "failed"
            await self.queue.update_item(item)
