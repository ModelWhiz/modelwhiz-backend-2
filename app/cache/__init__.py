"""
Cache module initialization
Provides unified access to caching functionality
"""
import logging

logger = logging.getLogger(__name__)

from .redis_client import cache_client

async def initialize_cache():
    """Initialize the global cache client"""
    try:
        await cache_client.initialize()
        logger.info("Cache initialized successfully")
    except Exception as e:
        logger.warning(f"Cache initialization failed: {e} - running in no-cache mode")

async def close_cache():
    """Close the global cache client"""
    try:
        await cache_client.close()
        logger.info("Cache closed successfully")
    except Exception as e:
        logger.warning(f"Cache close failed: {e}")

async def check_redis_health() -> bool:
    """Check Redis health"""
    try:
        return await cache_client.ping()
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False

# Helper functions for backward compatibility
async def get_cache(key: str):
    """Get value from cache"""
    return await cache_client.get(key)

async def set_cache(key: str, value, ttl: int = 300):
    """Set value in cache"""
    return await cache_client.set(key, value, expire=ttl)

async def delete_cache(key: str):
    """Delete key from cache"""
    return await cache_client.delete(key)

async def invalidate_cache_by_pattern(pattern: str):
    """Invalidate cache by pattern - not implemented in current Redis client"""
    # This would need to be implemented if pattern-based invalidation is needed
    logger.warning("Pattern-based cache invalidation not implemented")
    return 0

# Cache decorators and utilities
def cache_result(ttl: int = 300, key_generator=None):
    """Simple cache decorator"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # For now, just call the function without caching
            # TODO: Implement proper caching logic
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def invalidate_cache(*patterns):
    """Simple cache invalidation decorator"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # For now, just call the function without invalidation
            # TODO: Implement proper cache invalidation logic
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Cache key generators
def generate_model_list_key(*args, **kwargs) -> str:
    """Generate cache key for model list"""
    return f"models:list:{hash(str(args) + str(kwargs))}"

def generate_model_detail_key(model_id: str) -> str:
    """Generate cache key for model detail"""
    return f"model:detail:{model_id}"

def generate_model_invalidation_patterns(model_id: str) -> list:
    """Generate patterns for model cache invalidation"""
    return [f"model:*:{model_id}", f"models:list:*"]

def generate_user_invalidation_patterns(user_id: str) -> list:
    """Generate patterns for user cache invalidation"""
    return [f"user:*:{user_id}", f"models:list:*"]

# Cache TTL constants
MODEL_LIST_TTL = 300  # 5 minutes
MODEL_DETAIL_TTL = 600  # 10 minutes
EVALUATION_RESULT_TTL = 1800  # 30 minutes