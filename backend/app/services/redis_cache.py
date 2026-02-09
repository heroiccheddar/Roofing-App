"""Upstash Redis caching service.

Provides async caching for API responses to reduce database load.
Uses Upstash Redis HTTP client for serverless-friendly operation.
Gracefully degrades if Redis is unavailable.
"""

import json
import logging
from typing import Any, Optional

from upstash_redis import Redis

from app.config import settings

logger = logging.getLogger(__name__)

# Cache key prefixes
CACHE_PREFIX_GEOJSON = "geojson"
CACHE_PREFIX_ZONE_DETAIL = "zone"
CACHE_PREFIX_ZONE_LIST = "zonelist"

# TTLs in seconds
TTL_GEOJSON = 300  # 5 minutes
TTL_ZONE_DETAIL = 60  # 1 minute
TTL_ZONE_LIST = 120  # 2 minutes


class RedisCache:
    """Upstash Redis cache wrapper with graceful degradation."""

    def __init__(self):
        """Initialize Redis client. Handles missing config gracefully."""
        try:
            url = settings.UPSTASH_REDIS_URL
            token = settings.UPSTASH_REDIS_TOKEN

            if not url or not token:
                raise ValueError("Redis credentials not configured")

            self._client = Redis(url=url, token=token)
            self._available = True
            logger.info("Redis cache initialized")
        except Exception as e:
            self._client = None
            self._available = False
            logger.warning(f"Redis cache unavailable: {e}")

    @property
    def available(self) -> bool:
        """Check if Redis is available."""
        return self._available

    async def get(self, key: str) -> Optional[str]:
        """Get a value from cache. Returns None on miss or error."""
        if not self._available:
            return None
        try:
            result = self._client.get(key)
            return result
        except Exception as e:
            logger.warning(f"Redis GET failed for key {key}: {e}")
            return None

    async def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON from cache."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Redis GET_JSON deserialization failed for key {key}: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """Set a value in cache with TTL in seconds. Returns True on success."""
        if not self._available:
            return False
        try:
            self._client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for key {key}: {e}")
            return False

    async def set_json(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Serialize to JSON and set in cache."""
        try:
            serialized = json.dumps(value)
            return await self.set(key, serialized, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"Redis SET_JSON serialization failed for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns True on success."""
        if not self._available:
            return False
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE failed for key {key}: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern. Returns count deleted."""
        if not self._available:
            return 0
        try:
            # Upstash supports SCAN-based pattern deletion
            keys = []
            cursor = 0
            while True:
                cursor, batch = self._client.scan(cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break

            if keys:
                self._client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.warning(f"Redis INVALIDATE failed for pattern {pattern}: {e}")
            return 0


# Helper functions for building cache keys


def geojson_cache_key(user_id: str, min_score: float | None = None) -> str:
    """Build cache key for GeoJSON endpoint."""
    score_part = f":s{min_score}" if min_score is not None else ""
    return f"{CACHE_PREFIX_GEOJSON}:{user_id}{score_part}"


def zone_detail_cache_key(zone_id: str) -> str:
    """Build cache key for zone detail endpoint."""
    return f"{CACHE_PREFIX_ZONE_DETAIL}:{zone_id}"


def zone_list_cache_key(user_id: str, params_hash: str) -> str:
    """Build cache key for zone list endpoint."""
    return f"{CACHE_PREFIX_ZONE_LIST}:{user_id}:{params_hash}"


# Invalidation function for scoring pipeline


async def invalidate_zone_caches() -> int:
    """Invalidate all zone-related caches. Called after scoring pipeline runs."""
    count = 0
    count += await cache.invalidate_pattern(f"{CACHE_PREFIX_GEOJSON}:*")
    count += await cache.invalidate_pattern(f"{CACHE_PREFIX_ZONE_DETAIL}:*")
    count += await cache.invalidate_pattern(f"{CACHE_PREFIX_ZONE_LIST}:*")
    return count


# Module-level singleton instance
cache = RedisCache()
