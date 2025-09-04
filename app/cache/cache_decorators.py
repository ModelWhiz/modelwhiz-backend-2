"""
Cache decorators for automatic caching and invalidation
"""
import functools
import logging
from typing import Callable, List, Union, Any
from .redis_client import cache_client

logger = logging.getLogger(__name__)

def cache_result(ttl: int = 300, key_generator: Callable = None, compress: bool = True):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time-to-live in seconds (default: 5 minutes)
        key_generator: Function to generate cache key from args/kwargs
        compress: Whether to compress cached data (default: True for large data)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_generator:
                try:
                    cache_key = key_generator(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Key generation failed for {func.__name__}: {e}")
                    # Fall back to executing function without caching
                    return await func(*args, **kwargs)
            else:
                # Generate default key from function name and args
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try cache first
            try:
                cached_result = await cache_client.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache HIT for {func.__name__} (key: {cache_key})")
                    return cached_result
            except Exception as e:
                logger.error(f"Cache get failed for {func.__name__}: {e}")
            
            # Cache miss - execute function
            logger.debug(f"Cache MISS for {func.__name__} (key: {cache_key})")
            
            try:
                result = await func(*args, **kwargs)
                
                # Cache the result (don't cache None values)
                if result is not None:
                    # Check if result is already a dictionary (prevent double serialization)
                    if isinstance(result, list):
                        cache_value = [item.model_dump() if hasattr(item, 'model_dump') else item for item in result]
                    elif hasattr(result, 'model_dump'):
                        cache_value = result.model_dump()
                    else:
                        cache_value = result
                    
                    success = await cache_client.set(cache_key, cache_value, ttl)
                    if success:
                        logger.debug(f"Cached result for {func.__name__} (key: {cache_key})")
                    else:
                        logger.warning(f"Failed to cache result for {func.__name__}")
                
                return result
                
            except Exception as e:
                logger.error(f"Function execution failed for {func.__name__}: {e}")
                raise
        
        return wrapper
    return decorator

def invalidate_cache(patterns_generator: Callable = None):
    """
    Decorator to invalidate cache entries after function execution
    
    Args:
        patterns_generator: Function that generates list of cache patterns to invalidate
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Execute the original function first
                result = await func(*args, **kwargs)
                
                # Generate invalidation patterns
                if patterns_generator:
                    try:
                        patterns = patterns_generator(*args, **kwargs)
                        
                        if isinstance(patterns, str):
                            patterns = [patterns]
                        elif not isinstance(patterns, (list, tuple)):
                            patterns = []
                        
                        # Invalidate each pattern
                        total_invalidated = 0
                        for pattern in patterns:
                            if pattern:
                                count = await cache_client.invalidate_pattern(pattern)
                                total_invalidated += count
                        
                        if total_invalidated > 0:
                            logger.info(f"Invalidated {total_invalidated} cache entries for {func.__name__}")
                        
                    except Exception as e:
                        logger.error(f"Cache invalidation failed for {func.__name__}: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"Function execution failed for {func.__name__}: {e}")
                raise
        
        return wrapper
    return decorator

def cached_property(ttl: int = 600):
    """
    Decorator for caching expensive property calculations
    
    Args:
        ttl: Time-to-live in seconds (default: 10 minutes)
    """
    def decorator(func: Callable) -> property:
        @functools.wraps(func)
        async def wrapper(self):
            cache_key = f"{self.__class__.__name__}:{id(self)}:{func.__name__}"
            
            # Try cache first
            try:
                cached_result = await cache_client.get(cache_key)
                if cached_result is not None:
                    return cached_result
            except Exception as e:
                logger.error(f"Cache get failed for property {func.__name__}: {e}")
            
            # Calculate and cache
            result = await func(self)
            
            if result is not None:
                try:
                    await cache_client.set(cache_key, result, ttl)
                except Exception as e:
                    logger.error(f"Cache set failed for property {func.__name__}: {e}")
            
            return result
        
        return property(wrapper)
    return decorator

def cache_unless(condition: Callable) -> Callable:
    """
    Conditional caching decorator - only cache if condition is False
    
    Args:
        condition: Function that returns True to skip caching
    """
    def decorator(cache_decorator: Callable) -> Callable:
        def wrapper(func: Callable) -> Callable:
            cached_func = cache_decorator(func)
            
            @functools.wraps(func)
            async def inner(*args, **kwargs):
                # Check condition
                try:
                    skip_cache = condition(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Cache condition check failed: {e}")
                    skip_cache = False
                
                if skip_cache:
                    # Skip cache, execute directly
                    return await func(*args, **kwargs)
                else:
                    # Use cached version
                    return await cached_func(*args, **kwargs)
            
            return inner
        return wrapper
    return decorator

# Utility functions for common caching patterns

def is_development_mode() -> bool:
    """Check if running in development mode"""
    import os
    return os.getenv("ENVIRONMENT", "development").lower() == "development"

def is_user_authenticated(*args, **kwargs) -> bool:
    """Check if user is authenticated (skip cache for anonymous users)"""
    user_id = kwargs.get('user_id')
    if not user_id and args:
        if hasattr(args[0], 'user_id'):
            user_id = args[0].user_id
    
    return user_id is not None and user_id != 'anonymous'

# Pre-configured decorators for common use cases

# Cache for 5 minutes, skip in development
quick_cache = lambda key_gen: cache_unless(lambda *args, **kwargs: is_development_mode())(
    cache_result(ttl=300, key_generator=key_gen)
)

# Cache for 10 minutes, only for authenticated users
user_cache = lambda key_gen: cache_unless(lambda *args, **kwargs: not is_user_authenticated(*args, **kwargs))(
    cache_result(ttl=600, key_generator=key_gen)
)

# Long-term cache for expensive operations (1 hour)
long_cache = lambda key_gen: cache_result(ttl=3600, key_generator=key_gen)