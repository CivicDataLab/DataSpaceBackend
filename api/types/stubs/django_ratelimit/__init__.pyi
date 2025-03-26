from typing import Any, Callable, Optional, TypeVar, Union

from django.http import HttpRequest, HttpResponse

_F = TypeVar("_F", bound=Callable[..., Any])

def ratelimit(
    key: str = ...,
    rate: str = ...,
    method: Union[list[str], str] = ...,
    block: bool = ...,
    group: Optional[str] = ...,
) -> Callable[[_F], _F]: ...
