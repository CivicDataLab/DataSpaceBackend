CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",  # Using redis container hostname
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,
            "RETRY_ON_TIMEOUT": True,  # Added retry on timeout
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 100
            },  # Added connection pool settings
        },
    }
}

# Cache time to live is 15 minutes.
CACHE_TTL = 60 * 15

# Key prefix for cache keys
CACHE_KEY_PREFIX = "dataex"

# Session cache configuration
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Cache middleware settings
CACHE_MIDDLEWARE_SECONDS = 60 * 5  # 5 minutes
CACHE_MIDDLEWARE_KEY_PREFIX = "dataex"
