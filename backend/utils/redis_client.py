"""
Redis async client wrapper for caching and session management.

Provides connection pooling, health checks, and JSON serialization
for cache operations with graceful fallback if Redis is unavailable.
"""

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Global Redis client instance (singleton)
_redis_client = None


async def init_redis(redis_url: str) -> Optional[Any]:
    """
    Initialize Redis async client with connection pooling.

    Creates a new async Redis connection pool and performs health check.
    Handles graceful fallback if Redis is unavailable.

    Args:
        redis_url: Redis connection URL
                  Format: "redis://localhost:6379/0"
                  or "redis://:password@localhost:6379/0"

    Returns:
        redis.asyncio.Redis client instance or None if connection fails

    Raises:
        Exception: Logs but doesn't raise (graceful degradation)

    Features:
        - Connection pooling
        - Health check via PING
        - Graceful fallback if Redis unavailable
        - Async/await support

    Example:
        >>> redis_client = await init_redis("redis://localhost:6379/0")
        >>> if redis_client:
        ...     await redis_client.set("key", "value")
    """
    global _redis_client

    try:
        import redis.asyncio

        logger.info(f"Initializing Redis connection: {redis_url}")

        # Create Redis client with connection pooling
        _redis_client = redis.asyncio.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )

        # Perform health check
        is_healthy = await check_health()
        if is_healthy:
            logger.info("Redis connection initialized successfully")
            return _redis_client
        else:
            logger.warning("Redis health check failed. Closing connection.")
            await _redis_client.close()
            _redis_client = None
            return None

    except ImportError:
        logger.warning(
            "redis-py not installed. Install with: pip install redis[asyncio]"
        )
        return None
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}. Continuing without cache.")
        _redis_client = None
        return None


async def get_redis() -> Optional[Any]:
    """
    Get the cached Redis client instance.

    Returns the globally cached Redis client if available,
    None if Redis is not initialized or unavailable.

    Returns:
        redis.asyncio.Redis client instance or None

    Example:
        >>> redis_client = await get_redis()
        >>> if redis_client:
        ...     value = await redis_client.get("key")
    """
    return _redis_client


async def check_health() -> bool:
    """
    Perform health check on Redis connection.

    Sends PING command to Redis and checks response.
    Used during initialization and for monitoring.

    Returns:
        True if Redis is healthy and responding, False otherwise

    Example:
        >>> healthy = await check_health()
        >>> if healthy:
        ...     print("Redis is ready")
    """
    try:
        if _redis_client is None:
            logger.debug("Redis client not initialized")
            return False

        response = await _redis_client.ping()
        if response:
            logger.debug("Redis health check passed")
            return True
        else:
            logger.warning("Redis health check failed (no response)")
            return False

    except Exception as e:
        logger.warning(f"Redis health check error: {e}")
        return False


async def cache_set(
    key: str,
    value: Any,
    ttl: int = 300,
) -> bool:
    """
    Set a value in Redis cache with TTL.

    Serializes value to JSON and stores in Redis with optional expiration.
    Gracefully handles if Redis is unavailable.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time-to-live in seconds (default: 300)

    Returns:
        True if set successfully, False if Redis unavailable or error

    Example:
        >>> await cache_set("session_123", {"status": "active"}, ttl=3600)
    """
    try:
        if _redis_client is None:
            logger.debug(f"Redis not available, skipping cache set for key: {key}")
            return False

        # Serialize value to JSON
        if isinstance(value, str):
            json_value = value
        else:
            json_value = json.dumps(value, default=str)

        # Set with TTL
        await _redis_client.setex(
            key,
            ttl,
            json_value,
        )

        logger.debug(f"Cached value for key: {key} (ttl={ttl}s)")
        return True

    except json.JSONDecodeError as e:
        logger.error(f"JSON serialization error for key {key}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Redis cache_set error for key {key}: {e}")
        return False


async def cache_get(key: str) -> Optional[Any]:
    """
    Get a value from Redis cache.

    Retrieves value from Redis and deserializes from JSON.
    Returns None if key not found or Redis unavailable.

    Args:
        key: Cache key

    Returns:
        Deserialized value if found, None if not found or Redis unavailable

    Example:
        >>> value = await cache_get("session_123")
        >>> if value:
        ...     print(f"Session status: {value['status']}")
    """
    try:
        if _redis_client is None:
            logger.debug(f"Redis not available, skipping cache get for key: {key}")
            return None

        # Get value from Redis
        json_value = await _redis_client.get(key)

        if json_value is None:
            logger.debug(f"Cache miss for key: {key}")
            return None

        # Deserialize from JSON
        try:
            value = json.loads(json_value)
        except json.JSONDecodeError:
            # If not JSON, return as string
            value = json_value

        logger.debug(f"Cache hit for key: {key}")
        return value

    except Exception as e:
        logger.warning(f"Redis cache_get error for key {key}: {e}")
        return None


async def cache_delete(key: str) -> bool:
    """
    Delete a value from Redis cache.

    Args:
        key: Cache key to delete

    Returns:
        True if deleted successfully, False if key not found or error

    Example:
        >>> await cache_delete("session_123")
    """
    try:
        if _redis_client is None:
            logger.debug(f"Redis not available, skipping cache delete for key: {key}")
            return False

        count = await _redis_client.delete(key)
        if count > 0:
            logger.debug(f"Deleted key from cache: {key}")
            return True
        else:
            logger.debug(f"Key not found in cache: {key}")
            return False

    except Exception as e:
        logger.warning(f"Redis cache_delete error for key {key}: {e}")
        return False


async def cache_clear_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern from Redis cache.

    Args:
        pattern: Key pattern (e.g., "session:*", "detection:*")

    Returns:
        Number of keys deleted

    Example:
        >>> deleted = await cache_clear_pattern("session:*")
        >>> print(f"Deleted {deleted} session keys")
    """
    try:
        if _redis_client is None:
            logger.debug("Redis not available, skipping cache clear")
            return 0

        # Find keys matching pattern
        keys = await _redis_client.keys(pattern)

        if not keys:
            logger.debug(f"No keys found matching pattern: {pattern}")
            return 0

        # Delete matching keys
        count = await _redis_client.delete(*keys)
        logger.debug(f"Deleted {count} keys matching pattern: {pattern}")
        return count

    except Exception as e:
        logger.warning(f"Redis cache_clear_pattern error for pattern {pattern}: {e}")
        return 0


async def close_redis() -> None:
    """
    Close Redis connection and clean up resources.

    Should be called during application shutdown.

    Example:
        >>> await close_redis()
    """
    global _redis_client

    try:
        if _redis_client is not None:
            logger.info("Closing Redis connection")
            await _redis_client.close()
            _redis_client = None
            logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {e}")
