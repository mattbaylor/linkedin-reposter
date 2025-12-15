"""Database initialization and session management."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import event, text
from .models import Base
from .config import get_settings
import logging

logger = logging.getLogger(__name__)

# Global database engine and session maker
engine = None
async_session_maker = None


def get_database_url() -> str:
    """Get the database URL based on configuration."""
    settings = get_settings()
    # Using SQLite with aiosqlite async driver
    # Store database in /app/data volume mount
    return "sqlite+aiosqlite:///./data/linkedin_reposter.db"


async def init_db() -> None:
    """Initialize the database engine and create tables."""
    global engine, async_session_maker
    
    database_url = get_database_url()
    logger.info(f"🗄️  Initializing database: {database_url}")
    
    # Create async engine
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL query logging
        connect_args={
            "check_same_thread": False,
            # Enable foreign key constraints for SQLite
            "isolation_level": None,  # Required for PRAGMA to work
        },
        poolclass=StaticPool,  # Use StaticPool for SQLite
    )
    
    # Enable foreign key constraints for SQLite connections
    # This ensures referential integrity (cascading deletes, etc.)
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        # Enable foreign key constraints for this connection
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("✅ Database initialized successfully")


async def close_db() -> None:
    """Close database connections."""
    global engine
    
    if engine:
        logger.info("🗄️  Closing database connections...")
        await engine.dispose()
        logger.info("✅ Database connections closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.
    
    Usage in FastAPI:
        @app.get("/posts")
        async def get_posts(db: AsyncSession = Depends(get_db)):
            # Use db here
    """
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with async_session_maker() as session:
        try:
            # Enable foreign keys for this session (SQLite specific)
            await session.execute(text("PRAGMA foreign_keys=ON"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Utility functions for common database operations
async def get_session() -> AsyncSession:
    """Get a new database session (for use outside of FastAPI dependency injection)."""
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    return async_session_maker()
