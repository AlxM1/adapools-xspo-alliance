"""
FastAPI authentication dependencies.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, User, UserRole
from .service import auth_service


# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer_token: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    api_key: str = Depends(api_key_header),
) -> Optional[User]:
    """
    Get current user from JWT token or API key (optional).
    Returns None if no valid authentication provided.
    """
    # Try JWT token first
    if bearer_token:
        payload = auth_service.decode_access_token(bearer_token.credentials)
        if payload:
            user_id = UUID(payload["sub"])
            user = await auth_service.get_user_by_id(db, user_id)
            if user and user.is_active:
                return user

    # Try API key
    if api_key:
        user = await auth_service.verify_api_key(db, api_key)
        if user and user.is_active:
            return user

    return None


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """
    Get current user from JWT token or API key (required).
    Raises 401 if not authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Get current active user. Raises 403 if user is inactive."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return user


async def get_current_verified_user(
    user: User = Depends(get_current_active_user),
) -> User:
    """Get current verified user. Raises 403 if user is not verified."""
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    return user


async def get_current_admin_user(
    user: User = Depends(get_current_active_user),
) -> User:
    """Get current admin user. Raises 403 if not admin."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


class RoleChecker:
    """Dependency for checking user roles."""

    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    async def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' not authorized for this action",
            )
        return user


class ScopeChecker:
    """Dependency for checking API key scopes."""

    def __init__(self, required_scopes: list[str]):
        self.required_scopes = required_scopes

    async def __call__(
        self,
        db: AsyncSession = Depends(get_db),
        api_key: str = Depends(api_key_header),
        user: User = Depends(get_current_user),
    ) -> User:
        # If using API key, check scopes
        if api_key:
            from sqlalchemy import select
            from database import APIKey
            import hashlib

            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            result = await db.execute(
                select(APIKey).where(APIKey.key_hash == key_hash)
            )
            api_key_obj = result.scalar_one_or_none()

            if api_key_obj:
                for scope in self.required_scopes:
                    if scope not in (api_key_obj.scopes or []):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"API key missing required scope: {scope}",
                        )

        return user


# Convenience dependencies
require_admin = RoleChecker([UserRole.ADMIN])
require_user_or_admin = RoleChecker([UserRole.USER, UserRole.ADMIN])
require_read_scope = ScopeChecker(["read"])
require_write_scope = ScopeChecker(["write"])
