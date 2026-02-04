"""
Authentication service for JWT and API key authentication.
"""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.models import User, APIKey, RefreshToken, UserRole


class AuthService:
    """Authentication service for managing users, JWT tokens, and API keys."""

    def __init__(self):
        # JWT settings
        self.secret_key = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.refresh_token_expire_days = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

        # Password hashing
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # ============================================================
    # Password Hashing
    # ============================================================

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return self.pwd_context.verify(plain_password, hashed_password)

    # ============================================================
    # User Management
    # ============================================================

    async def create_user(
        self,
        db: AsyncSession,
        email: str,
        username: str,
        password: str,
        full_name: str = None,
        role: UserRole = UserRole.USER,
    ) -> User:
        """Create a new user."""
        # Check if user exists
        existing = await db.execute(
            select(User).where((User.email == email) | (User.username == username))
        )
        if existing.scalar_one_or_none():
            raise ValueError("User with this email or username already exists")

        user = User(
            email=email,
            username=username,
            password_hash=self.hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
            is_verified=False,
        )

        db.add(user)
        await db.flush()
        await db.refresh(user)

        logger.info(f"Created user: {username} ({email})")
        return user

    async def authenticate_user(
        self,
        db: AsyncSession,
        email_or_username: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate a user by email/username and password."""
        result = await db.execute(
            select(User).where(
                ((User.email == email_or_username) | (User.username == email_or_username))
                & (User.is_active == True)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not self.verify_password(password, user.password_hash):
            return None

        # Update last login
        user.last_login_at = datetime.utcnow()
        await db.flush()

        return user

    async def get_user_by_id(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    # ============================================================
    # JWT Tokens
    # ============================================================

    def create_access_token(self, user: User) -> str:
        """Create a JWT access token."""
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role.value,
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    async def create_refresh_token(
        self,
        db: AsyncSession,
        user: User,
        device_info: str = None,
        ip_address: str = None,
    ) -> str:
        """Create a refresh token and store in database."""
        token = secrets.token_urlsafe(64)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            device_info=device_info,
            ip_address=ip_address,
            expires_at=expires_at,
        )

        db.add(refresh_token)
        await db.flush()

        return token

    def decode_access_token(self, token: str) -> Optional[dict]:
        """Decode and validate an access token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    async def verify_refresh_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> Optional[User]:
        """Verify a refresh token and return the user."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await db.execute(
            select(RefreshToken).where(
                (RefreshToken.token_hash == token_hash)
                & (RefreshToken.expires_at > datetime.utcnow())
                & (RefreshToken.revoked_at == None)
            )
        )
        refresh_token = result.scalar_one_or_none()

        if not refresh_token:
            return None

        return await self.get_user_by_id(db, refresh_token.user_id)

    async def revoke_refresh_token(self, db: AsyncSession, token: str) -> bool:
        """Revoke a refresh token."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        refresh_token = result.scalar_one_or_none()

        if refresh_token:
            refresh_token.revoked_at = datetime.utcnow()
            await db.flush()
            return True

        return False

    async def revoke_all_user_tokens(self, db: AsyncSession, user_id: UUID):
        """Revoke all refresh tokens for a user."""
        result = await db.execute(
            select(RefreshToken).where(
                (RefreshToken.user_id == user_id)
                & (RefreshToken.revoked_at == None)
            )
        )
        tokens = result.scalars().all()

        for token in tokens:
            token.revoked_at = datetime.utcnow()

        await db.flush()
        logger.info(f"Revoked {len(tokens)} refresh tokens for user {user_id}")

    # ============================================================
    # API Keys
    # ============================================================

    async def create_api_key(
        self,
        db: AsyncSession,
        user: User,
        name: str,
        scopes: list[str] = None,
        expires_at: datetime = None,
    ) -> Tuple[str, APIKey]:
        """Create a new API key. Returns (plaintext_key, api_key_object)."""
        # Generate key
        key = f"nvp_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        key_prefix = key[:12]

        api_key = APIKey(
            user_id=user.id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or ["read", "write"],
            expires_at=expires_at,
            is_active=True,
        )

        db.add(api_key)
        await db.flush()
        await db.refresh(api_key)

        logger.info(f"Created API key '{name}' for user {user.username}")
        return key, api_key

    async def verify_api_key(self, db: AsyncSession, key: str) -> Optional[User]:
        """Verify an API key and return the associated user."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        key_prefix = key[:12]

        result = await db.execute(
            select(APIKey).where(
                (APIKey.key_hash == key_hash)
                & (APIKey.key_prefix == key_prefix)
                & (APIKey.is_active == True)
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()
        await db.flush()

        return await self.get_user_by_id(db, api_key.user_id)

    async def revoke_api_key(self, db: AsyncSession, key_id: UUID, user_id: UUID) -> bool:
        """Revoke an API key."""
        result = await db.execute(
            select(APIKey).where(
                (APIKey.id == key_id)
                & (APIKey.user_id == user_id)
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            api_key.is_active = False
            await db.flush()
            return True

        return False

    async def list_api_keys(self, db: AsyncSession, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        result = await db.execute(
            select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())


# Global auth service instance
auth_service = AuthService()
