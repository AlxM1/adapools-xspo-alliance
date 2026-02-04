"""
Rate limiting utilities for authentication endpoints.
Provides protection against brute force attacks.
"""

import time
from collections import defaultdict
from typing import Optional
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, status, Request


@dataclass
class RateLimitEntry:
    """Tracks rate limit state for a single key."""
    attempts: int = 0
    first_attempt_time: float = 0.0
    locked_until: float = 0.0


class RateLimiter:
    """
    In-memory rate limiter for protecting auth endpoints.

    For production with multiple instances, consider using Redis-based rate limiting.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,  # 5 minutes
        lockout_seconds: int = 900,  # 15 minutes lockout after max attempts
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._entries: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self._lock = Lock()

    def _get_key(self, identifier: str, action: str) -> str:
        """Generate a rate limit key."""
        return f"{action}:{identifier}"

    def _cleanup_expired(self) -> None:
        """Remove expired entries to prevent memory growth."""
        current_time = time.time()
        expired_keys = []

        for key, entry in self._entries.items():
            # Entry is expired if both the window and lockout have passed
            if (current_time > entry.first_attempt_time + self.window_seconds and
                current_time > entry.locked_until):
                expired_keys.append(key)

        for key in expired_keys:
            del self._entries[key]

    def check_rate_limit(
        self,
        identifier: str,
        action: str = "login",
    ) -> None:
        """
        Check if the identifier is rate limited.

        Args:
            identifier: User identifier (IP address, email, or username)
            action: The action being rate limited (login, register, etc.)

        Raises:
            HTTPException: If rate limited
        """
        key = self._get_key(identifier, action)
        current_time = time.time()

        with self._lock:
            # Periodic cleanup
            if len(self._entries) > 10000:
                self._cleanup_expired()

            entry = self._entries[key]

            # Check if currently locked out
            if current_time < entry.locked_until:
                remaining = int(entry.locked_until - current_time)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many attempts. Try again in {remaining} seconds.",
                    headers={"Retry-After": str(remaining)},
                )

            # Reset if window has passed
            if current_time > entry.first_attempt_time + self.window_seconds:
                entry.attempts = 0
                entry.first_attempt_time = current_time

    def record_attempt(
        self,
        identifier: str,
        action: str = "login",
        success: bool = False,
    ) -> None:
        """
        Record an authentication attempt.

        Args:
            identifier: User identifier
            action: The action being rate limited
            success: Whether the attempt was successful
        """
        key = self._get_key(identifier, action)
        current_time = time.time()

        with self._lock:
            entry = self._entries[key]

            if success:
                # Reset on successful attempt
                entry.attempts = 0
                entry.first_attempt_time = 0
                entry.locked_until = 0
                return

            # Initialize first attempt time if needed
            if entry.first_attempt_time == 0:
                entry.first_attempt_time = current_time

            entry.attempts += 1

            # Lock out if max attempts exceeded
            if entry.attempts >= self.max_attempts:
                entry.locked_until = current_time + self.lockout_seconds

    def get_remaining_attempts(
        self,
        identifier: str,
        action: str = "login",
    ) -> int:
        """Get remaining attempts before lockout."""
        key = self._get_key(identifier, action)

        with self._lock:
            entry = self._entries[key]
            return max(0, self.max_attempts - entry.attempts)

    def reset(self, identifier: str, action: str = "login") -> None:
        """Reset rate limit for an identifier (e.g., after password reset)."""
        key = self._get_key(identifier, action)

        with self._lock:
            if key in self._entries:
                del self._entries[key]


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.
    Handles proxies via X-Forwarded-For header.
    """
    # Check for proxy headers (in order of preference)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; the first is the client
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


# Global rate limiter instances
login_limiter = RateLimiter(
    max_attempts=5,
    window_seconds=300,  # 5 minutes
    lockout_seconds=900,  # 15 minutes
)

register_limiter = RateLimiter(
    max_attempts=3,
    window_seconds=3600,  # 1 hour
    lockout_seconds=3600,  # 1 hour
)

password_reset_limiter = RateLimiter(
    max_attempts=3,
    window_seconds=3600,  # 1 hour
    lockout_seconds=3600,  # 1 hour
)
