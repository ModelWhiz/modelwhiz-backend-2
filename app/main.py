# app/main.py

import asyncio
from datetime import datetime
import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import async database components and cache client
from .db.async_database import async_engine, get_async_db, check_database_health, dispose_async_engine
from .cache import initialize_cache, close_cache, check_redis_health

# Import Base from the original database module (where models are defined)
from .db.database import Base

from .api import auth, models, evaluations, storage
from .middleware.cache_middleware import CacheMiddleware
from .middleware.compression import CompressionMiddleware
from .tasks.cleanup_scheduler import startup_storage_management, shutdown_storage_management
from .middleware.error_handler import register_error_handlers, request_id_middleware, request_logging_middleware

logger = logging.getLogger(__name__)

# --- Application Lifecycle Management with asynccontextmanager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("🚀 Starting ModelWhiz API...")
    try:
        # Initialize cache with retry logic
        max_cache_retries = 3
        cache_retry_delay = 1
        
        for attempt in range(max_cache_retries):
            try:
                await initialize_cache()
                if await check_redis_health():
                    logger.info("✅ Redis cache initialized successfully.")
                    break
                else:
                    logger.warning(f"⚠️ Redis cache health check failed on attempt {attempt + 1}")
                    if attempt < max_cache_retries - 1:
                        await asyncio.sleep(cache_retry_delay)
                        cache_retry_delay *= 2
            except Exception as e:
                if attempt < max_cache_retries - 1:
                    logger.warning(f"⚠️ Cache initialization attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(cache_retry_delay)
                    cache_retry_delay *= 2
                else:
                    logger.warning(f"⚠️ Cache initialization failed after {max_cache_retries} attempts: {e} - running in no-cache mode.")
        
        # Initialize database with retry logic
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                async with async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ Database tables ensured.")
                
                await check_database_health()
                logger.info("✅ Database connection verified!")
                break  # Success, exit retry loop
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Database connection attempt {attempt + 1} failed: {e}")
                    logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"❌ Database initialization failed after {max_retries} attempts: {e}")
                    logger.warning("⚠️ Starting app without database - some features may not work")
                    # Don't raise the error, just log it and continue
        
        # Initialize storage management
        try:
            await startup_storage_management()
            logger.info("✅ Storage management initialized!")
        except Exception as e:
            logger.warning(f"⚠️ Storage management initialization failed: {e}")
        
    except Exception as e:
        logger.error(f"❌ FATAL: Application startup failed: {e}")
        logger.warning("⚠️ Starting app with limited functionality - some features may not work")
        # Don't raise the error, just log it and continue

    logger.info("🎯 ModelWhiz API is ready to serve requests!")
    yield
    
    # Shutdown storage management
    try:
        await shutdown_storage_management()
    except Exception as e:
        logger.warning(f"⚠️ Error during storage shutdown: {e}")
    
    logger.info("🛑 Shutting down ModelWhiz API...")
    try:
        await close_cache()
        logger.info("✅ Cache connections closed.")
        await dispose_async_engine()
        logger.info("✅ Database connections closed.")
    except Exception as e:
        logger.error(f"⚠️ Error during shutdown: {e}")
    logger.info("👋 ModelWhiz API shutdown complete.")

app = FastAPI(title="ModelWhiz API", lifespan=lifespan)

# --- CORS Middleware ---
# Get CORS origins from environment or use defaults
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request ID Middleware ---
app.middleware("http")(request_id_middleware)

# --- Request Logging Middleware ---
app.middleware("http")(request_logging_middleware)

# --- Cache Middleware ---
app.add_middleware(CacheMiddleware)

# --- Compression Middleware ---
compression_level = int(os.getenv("COMPRESSION_LEVEL", "6"))
min_size = int(os.getenv("MINIMUM_COMPRESSION_SIZE", "100"))
app.add_middleware(CompressionMiddleware, minimum_size=min_size, compression_level=compression_level)

# --- Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(evaluations.router, prefix="/api/evaluations", tags=["Evaluations"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])

# --- Static Files ---
upload_dir = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# --- Register Error Handlers ---
register_error_handlers(app)

# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint that verifies database and cache connectivity.
    """
    try:
        db_healthy = await check_database_health()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_healthy = False
    
    try:
        cache_healthy = await check_redis_health()
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        cache_healthy = False
    
    status_code = status.HTTP_200_OK if (db_healthy and cache_healthy) else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "healthy" if (db_healthy and cache_healthy) else "unhealthy",
        "database": "healthy" if db_healthy else "unhealthy", 
        "cache": "healthy" if cache_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# --- Performance Monitoring Endpoints ---
@app.get("/monitoring/errors")
async def get_error_monitoring_stats(
    time_window_minutes: int = 60,
    time_window_hours: int = 24
):
    """
    Get error monitoring statistics for the specified time windows.
    """
    try:
        from app.utils.error_monitor import get_error_stats, get_redis_error_stats
        
        # Get in-memory stats
        in_memory_stats = get_error_stats(time_window_minutes)
        
        # Get Redis stats if available
        try:
            redis_stats = await get_redis_error_stats(time_window_hours)
        except Exception as e:
            logger.warning(f"Failed to get Redis error stats: {e}")
            redis_stats = {"error": str(e)}
        
        return {
            "in_memory": in_memory_stats,
            "redis": redis_stats,
            "time_window_minutes": time_window_minutes,
            "time_window_hours": time_window_hours
        }
    except Exception as e:
        logger.error(f"Error getting monitoring stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get monitoring stats")

@app.get("/monitoring/performance")
async def get_performance_metrics():
    """
    Get performance metrics and statistics.
    """
    try:
        from app.utils.performance_monitor import get_performance_stats
        return await get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return {
            "error": "Performance monitoring not available",
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/monitoring/cache")
async def get_cache_stats():
    """
    Get cache statistics and performance metrics.
    """
    try:
        from app.cache.redis_client import cache_client
        
        if not cache_client._initialized or not cache_client.client:
            return {"cache_available": False}
        
        # Get basic cache info
        info = await cache_client.client.info()
        
        return {
            "cache_available": True,
            "stats": {
                "used_memory": info.get('used_memory_human', 'N/A'),
                "connected_clients": info.get('connected_clients', 0),
                "total_commands_processed": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "hit_rate": f"{(info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1)) * 100):.2f}%"
            }
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "cache_available": False,
            "error": str(e)
        }

# --- Root Endpoint ---
@app.get("/")
@app.head("/")
async def read_root():
    return {
        "message": "ModelWhiz backend is running", 
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }
