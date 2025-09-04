# app/db/async_database.py

import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# Retrieve DATABASE_URL from environment variables with fallback
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    # Provide a default SQLite database for development
    logger.warning("DATABASE_URL environment variable is not set. Using default SQLite database.")
    DATABASE_URL = "sqlite:///./test.db"

# --- Database engine setup ---
# Convert synchronous URL to asynchronous URL scheme
# For PostgreSQL: "postgresql://..." -> "postgresql+asyncpg://..."
# For SQLite: "sqlite://..." -> "sqlite+aiosqlite://..."
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("sqlite://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)
else:
    # Handle other databases or raise an error for unsupported ones
    logger.error(f"Unsupported database scheme in DATABASE_URL: {DATABASE_URL}")
    # Fallback to SQLite
    ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
    logger.info(f"Falling back to SQLite: {ASYNC_DATABASE_URL}")

logger.info(f"Using async database: {ASYNC_DATABASE_URL}")

# Configure async engine with appropriate settings for each database type
try:
    if ASYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
        # PostgreSQL-specific configuration
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")),
            future=True,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "timeout": int(os.getenv("DB_TIMEOUT", "30"))
            }
        )
    elif ASYNC_DATABASE_URL.startswith("sqlite+aiosqlite://"):
        # SQLite-specific configuration (no connection pooling needed)
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            future=True,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            # SQLite doesn't use connection pooling in the same way
            # and doesn't support timeout in connect_args
        )
    else:
        # Fallback configuration
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")),
            future=True,
            echo=os.getenv("DB_ECHO", "false").lower() == "true"
        )
    
    logger.info("Async database engine created successfully")
    
except Exception as e:
    logger.error(f"Failed to create async database engine: {e}")
    # Fallback to SQLite
    ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
    logger.info(f"Falling back to SQLite: {ASYNC_DATABASE_URL}")
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        future=True,
        echo=False
    )

# --- Session factory ---
# async_sessionmaker: A factory for new AsyncSession objects.
# expire_on_commit=False: This means objects won't be expired after commit.
#                         This can reduce database hits if you access attributes
#                         on objects after they've been committed, improving performance.
AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# --- Dependency function for FastAPI ---
async def get_async_db():
    """
    Dependency to get an asynchronous database session.
    Manages session lifecycle (creation and closing).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# --- Health check function ---
async def check_database_health(retries: int = 5, delay: int = 1):
    """
    Verifies database connectivity with retry logic.
    Raises an exception if connection cannot be established after retries.
    """
    for i in range(retries):
        try:
            async with AsyncSessionLocal() as session:
                # Execute a simple query to check connectivity
                await session.execute(text("SELECT 1"))
                logger.info("Database connection successful!")
                return True
        except OperationalError as e:
            if i < retries - 1:
                logger.warning(f"Database connection attempt {i + 1} failed: {e}. Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Database connection failed after {retries} attempts: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error during database health check: {e}")
            return False
    return False

# --- Engine disposal function ---
async def dispose_async_engine():
    """
    Properly dispose of the async engine to free up resources.
    """
    try:
        await async_engine.dispose()
        logger.info("Async database engine disposed successfully.")
    except Exception as e:
        logger.error(f"Error disposing async database engine: {e}")