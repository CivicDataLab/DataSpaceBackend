"""Type stubs for django-cors-headers"""

from typing import Any, List, Optional, Union

class CorsModel:
    """Stub for CorsModel"""

    pass

class CorsMiddleware:
    """Stub for CorsMiddleware"""

    def __init__(self, get_response: Any) -> None: ...
    def __call__(self, request: Any) -> Any: ...

def get_model() -> CorsModel: ...
def signals_handler(
    sender: Any, instance: Any, created: bool, **kwargs: Any
) -> None: ...
def cors_allow_migrated_resources(
    request: Any, response: Any, *args: Any, **kwargs: Any
) -> None: ...
def check_errors(app_configs: Optional[List[Any]], **kwargs: Any) -> List[Any]: ...
