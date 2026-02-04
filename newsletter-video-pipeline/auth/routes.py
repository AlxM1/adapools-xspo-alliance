"""
Authentication API routes.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, User, UserRole
from .service import auth_service
from .dependencies import get_current_user, get_current_active_user, get_current_admin_user
from .rate_limiter import (
    login_limiter,
    register_limiter,
    get_client_ip,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================
# Request/Response Models
# ============================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email_or_username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default=["read", "write"])
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(BaseModel):
    key: str  # Only returned once on creation
    api_key: APIKeyResponse


# ============================================================
# Routes
# ============================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    client_ip = get_client_ip(req)

    # Check rate limit before processing
    register_limiter.check_rate_limit(client_ip, "register")

    try:
        user = await auth_service.create_user(
            db=db,
            email=request.email,
            username=request.username,
            password=request.password,
            full_name=request.full_name,
        )
        # Record successful registration
        register_limiter.record_attempt(client_ip, "register", success=True)
        return user
    except ValueError as e:
        # Record failed attempt
        register_limiter.record_attempt(client_ip, "register", success=False)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Login with email/username and password."""
    client_ip = get_client_ip(req)

    # Check rate limit by both IP and username/email to prevent enumeration
    login_limiter.check_rate_limit(client_ip, "login")
    login_limiter.check_rate_limit(request.email_or_username, "login")

    user = await auth_service.authenticate_user(
        db=db,
        email_or_username=request.email_or_username,
        password=request.password,
    )

    if not user:
        # Record failed attempt for both IP and identifier
        login_limiter.record_attempt(client_ip, "login", success=False)
        login_limiter.record_attempt(request.email_or_username, "login", success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Record successful login
    login_limiter.record_attempt(client_ip, "login", success=True)
    login_limiter.record_attempt(request.email_or_username, "login", success=True)

    # Create tokens
    access_token = auth_service.create_access_token(user)
    refresh_token = await auth_service.create_refresh_token(
        db=db,
        user=user,
        device_info=req.headers.get("User-Agent"),
        ip_address=get_client_ip(req),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=auth_service.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    user = await auth_service.verify_refresh_token(db, request.refresh_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Revoke old refresh token
    await auth_service.revoke_refresh_token(db, request.refresh_token)

    # Create new tokens
    access_token = auth_service.create_access_token(user)
    new_refresh_token = await auth_service.create_refresh_token(
        db=db,
        user=user,
        device_info=req.headers.get("User-Agent"),
        ip_address=req.client.host if req.client else None,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=auth_service.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Logout and revoke refresh token."""
    await auth_service.revoke_refresh_token(db, request.refresh_token)
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Logout from all devices (revoke all refresh tokens)."""
    await auth_service.revoke_all_user_tokens(db, user.id)
    return {"message": "Successfully logged out from all devices"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    full_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update current user profile."""
    if full_name is not None:
        user.full_name = full_name

    await db.flush()
    await db.refresh(user)
    return user


@router.post("/me/change-password")
async def change_password(
    request: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Change current user's password."""
    if not auth_service.verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = auth_service.hash_password(request.new_password)
    await db.flush()

    # Revoke all refresh tokens for security
    await auth_service.revoke_all_user_tokens(db, user.id)

    return {"message": "Password changed successfully. Please login again."}


# ============================================================
# API Key Management
# ============================================================

@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List all API keys for current user."""
    keys = await auth_service.list_api_keys(db, user.id)
    return keys


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateAPIKeyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Create a new API key. The key is only shown once."""
    from datetime import timedelta

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    key, api_key = await auth_service.create_api_key(
        db=db,
        user=user,
        name=request.name,
        scopes=request.scopes,
        expires_at=expires_at,
    )

    return APIKeyCreatedResponse(
        key=key,
        api_key=APIKeyResponse.model_validate(api_key),
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Revoke an API key."""
    success = await auth_service.revoke_api_key(db, key_id, user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return {"message": "API key revoked successfully"}


# ============================================================
# Admin Routes
# ============================================================

@router.get("/admin/users", response_model=list[UserResponse])
async def admin_list_users(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """List all users (admin only)."""
    from sqlalchemy import select

    result = await db.execute(
        select(User).offset(skip).limit(limit).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


@router.put("/admin/users/{user_id}/role")
async def admin_update_user_role(
    user_id: UUID,
    role: UserRole,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Update a user's role (admin only)."""
    user = await auth_service.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change own role")

    user.role = role
    await db.flush()

    return {"message": f"User role updated to {role.value}"}


@router.put("/admin/users/{user_id}/status")
async def admin_update_user_status(
    user_id: UUID,
    is_active: bool,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Enable/disable a user account (admin only)."""
    user = await auth_service.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable own account")

    user.is_active = is_active
    await db.flush()

    return {"message": f"User {'enabled' if is_active else 'disabled'}"}
