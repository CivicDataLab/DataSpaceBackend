"""Type stubs for django-cors-headers.conf"""

from typing import Any, List, Optional, Set, Union

from django.conf import settings

CORS_ALLOW_ALL_ORIGINS: bool
CORS_ALLOWED_ORIGINS: List[str]
CORS_ALLOWED_ORIGIN_REGEXES: List[str]
CORS_ALLOW_METHODS: List[str]
CORS_ALLOW_HEADERS: List[str]
CORS_ALLOW_CREDENTIALS: bool
CORS_PREFLIGHT_MAX_AGE: int
CORS_EXPOSE_HEADERS: List[str]
CORS_URLS_REGEX: str
