import json
import pickle
import hashlib
import functools
import logging
from typing import Any, Optional, Union, Callable, Dict
from datetime import timedelta
import redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis caching service with fallback support and multiple serialization options.
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = False,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        socket_timeout: int = 5,
        connection_pool_kwargs: Optional[Dict] = None
    ):
        """
        Initialize the cache service with Redis connection parameters.
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            decode_responses: Whether to decode responses from Redis
            max_retries: Maximum number of connection retries
            retry_delay: Delay between retries in seconds
            socket_timeout: Socket timeout in seconds
            connection_pool_kwargs: Additional connection pool arguments
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.decode_responses = decode_responses
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._redis_client = None
        self._is_available = True
        
        # Connection pool configuration
        pool_kwargs = {
            'host': host,
            'port': port,
            'db': db,
            'password': password,
            'decode_responses': decode_responses,
            'socket_timeout': socket_timeout,
            'socket_connect_timeout': socket_timeout,
            'retry_on_timeout': True,
            'max_connections': 50
        }
        
        if connection_pool_kwargs:
            pool_kwargs.update(connection_pool_kwargs)
            
        try:
            self._connection_pool = redis.ConnectionPool(**pool_kwargs)
            self._connect()
        except Exception as e:
            logger.warning(f"Failed to initialize Redis connection: {e}")
            self._is_available = False
    
    def _connect(self) -> Optional[redis.Redis]:
        """
        Establish connection to Redis with retry logic.
        
        Returns:
            Redis client instance or None if connection fails
        """
        if not self._is_available:
            return None
            
        for attempt in range(self.max_retries):
            try:
                if not self._redis_client:
                    self._redis_client = redis.Redis(connection_pool=self._connection_pool)
                
                # Test connection
                self._redis_client.ping()
                self._is_available = True
                return self._redis_client
                
            except (RedisError, RedisConnectionError, Exception) as e:
                logger.warning(f"Redis connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error("Redis connection failed after all retries. Falling back to no-cache mode.")
                    self._is_available = False
                    self._redis_client = None
                    
        return None
    
    def _serialize(self, value: Any, serialization: str = 'json') -> bytes:
        """
        Serialize value for storage in Redis.
        
        Args:
            value: Value to serialize
            serialization: Serialization method ('json' or 'pickle')
            
        Returns:
            Serialized bytes
        """
        if serialization == 'json':
            return json.dumps(value).encode('utf-8')
        elif serialization == 'pickle':
            return pickle.dumps(value)
        else:
            raise ValueError(f"Unsupported serialization method: {serialization}")
    
    def _deserialize(self, data: bytes, serialization: str = 'json') -> Any:
        """
        Deserialize value from Redis storage.
        
        Args:
            data: Serialized data
            serialization: Serialization method ('json' or 'pickle')
            
        Returns:
            Deserialized value
        """
        if data is None:
            return None
            
        if serialization == 'json':
            return json.loads(data.decode('utf-8'))
        elif serialization == 'pickle':
            return pickle.loads(data)
        else:
            raise ValueError(f"Unsupported serialization method: {serialization}")
    
    def generate_key(self, *args, prefix: str = '', **kwargs) -> str:
        """
        Generate a cache key from arguments.
        
        Args:
            *args: Positional arguments to include in key
            prefix: Optional prefix for the key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            Generated cache key
        """
        # Create a string representation of all arguments
        key_parts = []
        
        if prefix:
            key_parts.append(prefix)
            
        # Add positional arguments
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                # For complex objects, use hash
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])
        
        # Add keyword arguments (sorted for consistency)
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                key_parts.append(f"{k}:{v}")
            else:
                key_parts.append(f"{k}:{hashlib.md5(str(v).encode()).hexdigest()[:8]}")
                
        return ":".join(key_parts)
    
    def get(
        self,
        key: str,
        default: Any = None,
        serialization: str = 'json'
    ) -> Any:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            default: Default value if key not found
            serialization: Deserialization method
            
        Returns:
            Cached value or default
        """
        if not self._is_available:
            return default
            
        client = self._connect()
        if not client:
            return default
            
        try:
            data = client.get(key)
            if data is None:
                return default
            return self._deserialize(data, serialization)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return default
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[Union[int, timedelta]] = None,
        serialization: str = 'json'
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live (seconds or timedelta)
            serialization: Serialization method
            
        Returns:
            True if successful, False otherwise
        """
        if not self._is_available:
            return False
            
        client = self._connect()
        if not client:
            return False
            
        try:
            data = self._serialize(value, serialization)
            
            if ttl is None:
                return bool(client.set(key, data))
            else:
                if isinstance(ttl, timedelta):
                    ttl = int(ttl.total_seconds())
                return bool(client.setex(key, ttl, data))
                
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        """
        Delete one or more keys from cache.
        
        Args:
            *keys: Cache keys to delete
            
        Returns:
            Number of keys deleted
        """
        if not self._is_available or not keys:
            return 0
            
        client = self._connect()
        if not client:
            return 0
            
        try:
            return client.delete(*keys)
        except Exception as e:
            logger.error(f"Cache delete error for keys {keys}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self._is_available:
            return False
            
        client = self._connect()
        if not client:
            return False
            
        try:
            return bool(client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def expire(self, key: str, ttl: Union[int, timedelta]) -> bool:
        """
        Set expiration time for a key.
        
        Args:
            key: Cache key
            ttl: Time to live (seconds or timedelta)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._is_available:
            return False
            
        client = self._connect()
        if not client:
            return False
            
        try:
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
            return bool(client.expire(key, ttl))
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., "user:*")
            
        Returns:
            Number of keys deleted
        """
        if not self._is_available:
            return 0
            
        client = self._connect()
        if not client:
            return 0
            
        try:
            keys = client.keys(pattern)
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache clear pattern error for pattern {pattern}: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """
        Clear all keys in the current database.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._is_available:
            return False
            
        client = self._connect()
        if not client:
            return False
            
        try:
            client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Cache clear all error: {e}")
            return False
    
    def mget(self, keys: list, serialization: str = 'json') -> Dict[str, Any]:
        """
        Get multiple values from cache.
        
        Args:
            keys: List of cache keys
            serialization: Deserialization method
            
        Returns:
            Dictionary of key-value pairs
        """
        if not self._is_available or not keys:
            return {}
            
        client = self._connect()
        if not client:
            return {}
            
        try:
            values = client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value, serialization)
            return result
        except Exception as e:
            logger.error(f"Cache mget error for keys {keys}: {e}")
            return {}
    
    def mset(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[Union[int, timedelta]] = None,
        serialization: str = 'json'
    ) -> bool:
        """
        Set multiple key-value pairs in cache.
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live for all keys
            serialization: Serialization method
            
        Returns:
            True if successful, False otherwise
        """
        if not self._is_available or not mapping:
            return False
            
        client = self._connect()
        if not client:
            return False
            
        try:
            # Serialize all values
            serialized_mapping = {
                key: self._serialize(value, serialization)
                for key, value in mapping.items()
            }
            
            if ttl is None:
                return bool(client.mset(serialized_mapping))
            else:
                # For TTL, we need to set each key individually
                pipe = client.pipeline()
                if isinstance(ttl, timedelta):
                    ttl = int(ttl.total_seconds())
                    
                for key, value in serialized_mapping.items():
                    pipe.setex(key, ttl, value)
                    
                pipe.execute()
                return True
                
        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            return False
    
    def cached(
        self,
        ttl: Optional[Union[int, timedelta]] = 3600,
        key_prefix: str = '',
        serialization: str = 'json',
        include_kwargs: bool = True
    ) -> Callable:
        """
        Decorator for caching function results.
        
        Args:
            ttl: Time to live for cached results
            key_prefix: Prefix for cache keys
            serialization: Serialization method
            include_kwargs: Whether to include kwargs in cache key
            
        Returns:
            Decorated function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key_parts = [key_prefix or func.__name__]
                
                # Add args to key
                if args:
                    cache_key_parts.extend(str(arg) for arg in args)
                
                # Add kwargs to key if requested
                if include_kwargs and kwargs:
                    cache_key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                
                cache_key = self.generate_key(*cache_key_parts)
                
                # Try to get from cache
                cached_value = self.get(cache_key, serialization=serialization)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__} with key {cache_key}")
                    return cached_value
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Store in cache
                if result is not None:
                    self.set(cache_key, result, ttl=ttl, serialization=serialization)
                    logger.debug(f"Cached result for {func.__name__} with key {cache_key}")
                
                return result
                
            # Add cache management methods
            wrapper.cache_key = lambda *args, **kwargs: self.generate_key(
                key_prefix or func.__name__,
                *args,
                **kwargs if include_kwargs else {}
            )
            wrapper.invalidate = lambda *args, **kwargs: self.delete(
                wrapper.cache_key(*args, **kwargs)
            )
            wrapper.cache_service = self
            
            return wrapper
        return decorator
    
    def invalidate_group(self, group_prefix: str) -> int:
        """
        Invalidate all cache entries with a specific group prefix.
        
        Args:
            group_prefix: Group prefix to invalidate
            
        Returns:
            Number of keys invalidated
        """
        return self.clear_pattern(f"{group_prefix}*")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the cache service.
        
        Returns:
            Health status dictionary
        """
        client = self._connect()
        
        if not client:
            return {
                'status': 'unavailable',
                'redis_connected': False,
                'error': 'Cannot connect to Redis'
            }
            
        try:
            # Ping Redis
            client.ping()
            
            # Get Redis info
            info = client.info()
            
            return {
                'status': 'healthy',
                'redis_connected': True,
                'redis_version': info.get('redis_version'),
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human'),
                'db_keys': client.dbsize()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'redis_connected': False,
                'error': str(e)
            }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        if self._redis_client:
            self._redis_client.close()


# Singleton instance for easy import
_cache_service_instance = None


def get_cache_service(**kwargs) -> CacheService:
    """
    Get or create a singleton cache service instance.
    
    Args:
        **kwargs: Arguments to pass to CacheService constructor
        
    Returns:
        CacheService instance
    """
    global _cache_service_instance
    
    if _cache_service_instance is None:
        _cache_service_instance = CacheService(**kwargs)
        
    return _cache_service_instance


# Example usage and patterns
if __name__ == "__main__":
    # Initialize cache service
    cache = CacheService(host='localhost', port=6379)
    
    # Basic operations
    cache.set('user:123', {'name': 'John', 'email': 'john@example.com'}, ttl=3600)
    user = cache.get('user:123')
    print(f"User: {user}")
    
    # Using decorator
    @cache.cached(ttl=300, key_prefix='api_response')
    def fetch_api_data(endpoint: str, params: dict) -> dict:
        # Simulate API call
        import time
        time.sleep(1)
        return {'endpoint': endpoint, 'data': 'sample data'}
    
    # First call - will execute function
    result1 = fetch_api_data('/users', {'page': 1})
    
    # Second call - will return from cache
    result2 = fetch_api_data('/users', {'page': 1})
    
    # Invalidate specific cache entry
    fetch_api_data.invalidate('/users', {'page': 1})
    
    # Pattern-based invalidation
    cache.invalidate_group('user:')
    
    # Health check
    health = cache.health_check()
    print(f"Cache health: {health}")