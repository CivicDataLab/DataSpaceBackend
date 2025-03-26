from datetime import datetime
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)

import strawberry
from django.db.models import Model, QuerySet
from strawberry_django.fields.field import StrawberryDjangoField

T = TypeVar("T", bound="BaseType")
M = TypeVar("M", bound=Model)


class BaseType:
    """Base class for all GraphQL types with helper methods for Django model conversion."""

    @classmethod
    def from_django(cls: Type[T], instance: M) -> T:
        """Convert a Django model instance to a Strawberry type."""
        if not instance:
            raise ValueError(f"Cannot convert None to {cls.__name__}")

        data: Dict[str, Any] = {
            field.name: getattr(instance, field.name) for field in instance._meta.fields
        }

        try:
            return cast(T, instance)  # Explicitly cast to the correct type
        except TypeError as e:
            raise ValueError(f"Failed to create {cls.__name__} from data: {data}")

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> Optional[T]:
        """Create an instance from a dictionary."""
        if not data:
            return None

        try:
            return cls(**data)  # Explicitly instantiate the class
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def from_django_list(
        cls: Type[T], instances: Union[Sequence[M], QuerySet[M]]
    ) -> List[T]:
        """Convert a list or QuerySet of Django model instances to Strawberry types."""
        # return [cls.from_django(instance) for instance in instances]
        return cast(List[T], instances)
