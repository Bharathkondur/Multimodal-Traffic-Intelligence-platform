"""
Utilities package for Multimodal Traffic Intelligence Platform.

Exports utility functions for Redis caching and other helper functions.
"""

from .redis_client import (
    init_redis,
    get_redis,
    check_health,
    cache_set,
    cache_get,
)

__all__ = [
    "init_redis",
    "get_redis",
    "check_health",
    "cache_set",
    "cache_get",
]
