"""
QuantEngine Pro - Cache Manager
================================
Three-tier caching system:
1. Memory LRU cache (fastest, limited size) - process-level
2. Redis cache (fast, shared) - for hot data, 7-day TTL
3. Parquet files (slow, persistent) - for cold/archived data

Cache key generation: md5(symbol_freq_start_end)
"""

import hashlib
import json
import pickle
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd
from loguru import logger


# =============================================================================
# Memory LRU Cache
# =============================================================================

class LRUCache:
    """
    Simple LRU (Least Recently Used) in-memory cache.

    Thread-safe for single-process use. Uses OrderedDict to track access order.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries before eviction
        """
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache. Moves key to end (most recently used).

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """
        Store value in cache. Evicts least recently used if at capacity.

        Args:
            key: Cache key
            value: Value to store
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                # Evict least recently used (first item)
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"LRU evicted: {evicted_key}")
            self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("LRU cache cleared")

    def stats(self) -> Dict:
        """Get cache hit/miss statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


# =============================================================================
# Redis Cache (Optional)
# =============================================================================

class RedisCache:
    """
    Redis-based cache for shared hot data.

    Supports TTL-based expiration. Falls back gracefully if Redis is unavailable.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        default_ttl: int = 86400 * 7,  # 7 days
    ):
        """
        Initialize Redis cache.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            default_ttl: Default TTL in seconds
        """
        self.default_ttl = default_ttl
        self._redis = None
        self._enabled = False

        try:
            import redis
            self._redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=False,  # Keep bytes for pickle
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis.ping()
            self._enabled = True
            logger.info(f"Redis cache connected: {host}:{port}/{db}")
        except Exception as e:
            logger.warning(
                f"Redis not available ({e}), Redis cache disabled. "
                "System will use memory + file cache only."
            )

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """
        Get DataFrame from Redis.

        Args:
            key: Cache key

        Returns:
            DataFrame or None
        """
        if not self._enabled:
            return None

        try:
            data = self._redis.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            logger.debug(f"Redis get failed for {key}: {e}")
            return None

    def put(self, key: str, df: pd.DataFrame, ttl: Optional[int] = None) -> None:
        """
        Store DataFrame in Redis with TTL.

        Args:
            key: Cache key
            df: DataFrame to store
            ttl: TTL in seconds, uses default_ttl if not specified
        """
        if not self._enabled:
            return

        try:
            data = pickle.dumps(df, protocol=pickle.HIGHEST_PROTOCOL)
            self._redis.setex(
                key,
                ttl or self.default_ttl,
                data,
            )
        except Exception as e:
            logger.debug(f"Redis put failed for {key}: {e}")

    @property
    def enabled(self) -> bool:
        """Check if Redis is available."""
        return self._enabled


# =============================================================================
# Three-Tier Cache Manager
# =============================================================================

class CacheManager:
    """
    Three-tier cache manager implementing the full caching strategy.

    Lookup order: Memory → Redis → Parquet
    Store order: Memory + Redis + Parquet (write-through)

    Usage:
        cm = CacheManager()
        df = cm.get("key")
        if df is None:
            df = fetch_from_source()
            cm.put("key", df)
    """

    def __init__(
        self,
        memory_size: int = 1000,
        redis_config: Optional[Dict] = None,
        parquet_path: str = "./data/parquet",
    ):
        """
        Initialize three-tier cache.

        Args:
            memory_size: LRU cache max entries
            redis_config: Redis connection config dict
            parquet_path: Path for Parquet file storage
        """
        self.memory = LRUCache(max_size=memory_size)
        self.redis = RedisCache(**(redis_config or {}))
        self.parquet_path = parquet_path
        logger.info(
            f"CacheManager initialized: memory={memory_size}, "
            f"redis={'enabled' if self.redis.enabled else 'disabled'}"
        )

    @staticmethod
    def make_key(
        symbol: str,
        freq: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """
        Generate deterministic cache key.

        Args:
            symbol: Trading symbol
            freq: Data frequency
            start_date: Start date
            end_date: End date

        Returns:
            MD5 hash string as cache key
        """
        raw = f"{symbol}_{freq}_{start_date or ''}_{end_date or ''}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str, allow_parquet: bool = True) -> Optional[pd.DataFrame]:
        """
        Get data from cache, checking all tiers in order.

        Args:
            key: Cache key
            allow_parquet: If False, skip Parquet tier

        Returns:
            DataFrame or None if not found
        """
        # Tier 1: Memory
        result = self.memory.get(key)
        if result is not None:
            logger.debug(f"Cache HIT (memory): {key[:16]}...")
            return result

        # Tier 2: Redis
        result = self.redis.get(key)
        if result is not None:
            logger.debug(f"Cache HIT (redis): {key[:16]}...")
            # Promote to memory
            self.memory.put(key, result)
            return result

        # Tier 3: Parquet
        if allow_parquet:
            from quantengine.data.storage import ParquetStorage
            result = ParquetStorage.load(self.parquet_path, key)
            if result is not None and not result.empty:
                logger.debug(f"Cache HIT (parquet): {key[:16]}...")
                # Promote to memory
                self.memory.put(key, result)
                # Optionally promote to Redis
                self.redis.put(key, result)
                return result

        logger.debug(f"Cache MISS: {key[:16]}...")
        return None

    def put(
        self,
        key: str,
        df: pd.DataFrame,
        ttl: Optional[int] = None,
        persist: bool = True,
    ) -> None:
        """
        Store data in all cache tiers (write-through).

        Args:
            key: Cache key
            df: DataFrame to store
            ttl: Redis TTL in seconds
            persist: If True, also write to Parquet
        """
        if df is None or df.empty:
            return

        # Tier 1: Memory (always)
        self.memory.put(key, df)

        # Tier 2: Redis
        self.redis.put(key, df, ttl)

        # Tier 3: Parquet
        if persist:
            from quantengine.data.storage import ParquetStorage
            ParquetStorage.save(df, self.parquet_path, key)

    def clear_memory(self) -> None:
        """Clear memory cache only."""
        self.memory.clear()

    def stats(self) -> Dict:
        """Get cache statistics across all tiers."""
        return {
            "memory": self.memory.stats(),
            "redis_enabled": self.redis.enabled,
        }


# =============================================================================
# Decorator for caching function results
# =============================================================================

def cached(cache_manager: CacheManager, key_prefix: str = ""):
    """
    Decorator to cache function return values (DataFrames).

    Usage:
        @cached(cache_manager, "kline")
        async def fetch_kline(symbol, freq, start, end):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function arguments
            arg_str = f"{key_prefix}_{args}_{kwargs}"
            key = hashlib.md5(arg_str.encode()).hexdigest()

            # Check cache
            result = cache_manager.get(key)
            if result is not None:
                return result

            # Execute function and cache result
            result = await func(*args, **kwargs)
            if isinstance(result, pd.DataFrame) and not result.empty:
                cache_manager.put(key, result)
            return result

        return wrapper
    return decorator
