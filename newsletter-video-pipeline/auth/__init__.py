"""Authentication package."""

from .service import auth_service, AuthService
from .dependencies import (
    get_current_user,
    get_current_user_optional,
    get_current_active_user,
    get_current_verified_user,
    get_current_admin_user,
    RoleChecker,
    ScopeChecker,
    require_admin,
    require_user_or_admin,
    require_read_scope,
    require_write_scope,
)
from .routes import router as auth_router

__all__ = [
    "auth_service",
    "AuthService",
    "get_current_user",
    "get_current_user_optional",
    "get_current_active_user",
    "get_current_verified_user",
    "get_current_admin_user",
    "RoleChecker",
    "ScopeChecker",
    "require_admin",
    "require_user_or_admin",
    "require_read_scope",
    "require_write_scope",
    "auth_router",
]
