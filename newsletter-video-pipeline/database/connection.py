"""
Database connection and session management.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
from loguru import logger

from .models import Base


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://nvp:nvp_password@localhost:5432/newsletter_video_pipeline"
        )
        self.engine: AsyncEngine = None
        self.session_factory: async_sessionmaker = None

    async def initialize(self):
        """Initialize database connection pool."""
        logger.info(f"Initializing database connection...")

        # Create async engine
        self.engine = create_async_engine(
            self.database_url,
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.getenv("DATABASE_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DATABASE_POOL_RECYCLE", "1800")),
        )

        # Create session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        logger.info("Database connection initialized")

    async def create_tables(self):
        """Create all tables (for development only)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def drop_tables(self):
        """Drop all tables (dangerous - for development only)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("Database tables dropped")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions in FastAPI."""
    async with db_manager.session() as session:
        yield session
