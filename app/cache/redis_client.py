"""
Redis client for caching operations with async support
"""
import json
import gzip
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
import redis.asyncio as redis
from redis.asyncio import ConnectionPool
import os

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self):
        self.pool = None
        self.client = None
        self._initialized = False
        self._connection_failed = False
        
    async def initialize(self):
        """Initialize Redis connection pool"""
        if self._initialized:
            return
            
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        
        try:
            # Parse Redis URL to handle authentication properly
            if ":" in redis_url and "@" in redis_url:
                # URL format: redis://:password@host:port/db
                self.pool = ConnectionPool.from_url(
                    redis_url,
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
                    retry_on_timeout=True,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
                    decode_responses=False,  # We handle our own decoding
                    socket_connect_timeout=10,
                    socket_timeout=10
                )
            else:
                # Simple URL format: redis://host:port
                self.pool = ConnectionPool.from_url(
                    redis_url,
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
                    retry_on_timeout=True,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
                    decode_responses=False
                )
            
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Test connection
            await self.client.ping()
            logger.info("Redis connection established successfully")
            self._initialized = True
            self._connection_failed = False
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connection_failed = True
            # Fallback to no-op mode - don't mark as initialized if connection failed
            self.client = None
            if self.pool:
                try:
                    await self.pool.disconnect()
                except Exception:
                    pass
                self.pool = None
            self._initialized = False
            
    async def close(self):
        """Close Redis connection"""
        try:
            if self.client:
                await self.client.close()
            if self.pool:
                await self.pool.disconnect()
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
        finally:
            self._initialized = False
            self._connection_failed = False
            
    def _serialize(self, value: Any, compress: bool = False) -> bytes:
        """Serialize value to bytes with optional compression"""
        try:
            if isinstance(value, (str, int, float, bool)):
                data = json.dumps(value).encode('utf-8')
            else:
                # Handle datetime objects and complex types
                serialized = self._convert_datetime(value)
                data = json.dumps(serialized, default=str).encode('utf-8')
                
            # Compress if data is large or explicitly requested
            if compress or len(data) > int(os.getenv("REDIS_COMPRESSION_THRESHOLD", "1024")):
                data = gzip.compress(data)
                
            return data
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            raise
            
    def _deserialize(self, data: bytes, decompress: bool = False) -> Any:
        """Deserialize bytes to Python object"""
        try:
            # Auto-detect compression by checking gzip magic number
            if data.startswith(b'\x1f\x8b') or decompress:
                data = gzip.decompress(data)
                
            decoded_str = data.decode('utf-8')
            return json.loads(decoded_str)
                
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return None
            
    def _convert_datetime(self, obj: Any) -> Any:
        """Convert datetime objects to ISO format for serialization"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_datetime(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetime(item) for item in obj]
        return obj
        
    async def set(self, key: str, value: Any, expire: Optional[int] = None, compress: bool = False) -> bool:
        """Set a key-value pair in Redis"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping set operation")
            return False
            
        try:
            serialized_value = self._serialize(value, compress)
            result = await self.client.set(key, serialized_value, ex=expire)
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            return False
            
    async def get(self, key: str, decompress: bool = False) -> Optional[Any]:
        """Get a value from Redis by key"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping get operation")
            return None
            
        try:
            value = await self.client.get(key)
            if value is None:
                return None
            return self._deserialize(value, decompress)
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None
            
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping delete operation")
            return False
            
        try:
            result = await self.client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False
            
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping exists operation")
            return False
            
        try:
            result = await self.client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error checking existence of key {key}: {e}")
            return False
            
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for a key"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping expire operation")
            return False
            
        try:
            result = await self.client.expire(key, seconds)
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting expiration for key {key}: {e}")
            return False
            
    async def ttl(self, key: str) -> int:
        """Get time to live for a key"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping TTL operation")
            return -2
            
        try:
            return await self.client.ttl(key)
        except Exception as e:
            logger.error(f"Error getting TTL for key {key}: {e}")
            return -2
            
    async def flushdb(self) -> bool:
        """Clear all keys from the current database"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping flush operation")
            return False
            
        try:
            await self.client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Error flushing database: {e}")
            return False
            
    async def info(self) -> Dict[str, Any]:
        """Get Redis server information"""
        if not self._initialized or self._connection_failed:
            logger.warning("Redis not available, skipping info operation")
            return {}
            
        try:
            return await self.client.info()
        except Exception as e:
            logger.error(f"Error getting Redis info: {e}")
            return {}
            
    async def ping(self) -> bool:
        """Ping Redis server"""
        if not self._initialized or self._connection_failed:
            return False
            
        try:
            result = await self.client.ping()
            # Handle both string and bytes responses
            if isinstance(result, bytes):
                return result == b'PONG'
            elif isinstance(result, str):
                return result == 'PONG'
            else:
                return bool(result)
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

# Global Redis client instance
cache_client = RedisClient()