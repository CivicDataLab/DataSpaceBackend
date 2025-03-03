from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar, cast

import strawberry
from django.db.models import Model, QuerySet
from strawberry_django.fields.field import StrawberryDjangoField

T = TypeVar("T", bound="BaseType")
M = TypeVar("M", bound=Model)


@strawberry.interface
class BaseType:
    """Base interface for all GraphQL types."""

    @classmethod
    def from_django(cls: Type[T], instance: M) -> T:
        """Convert Django model instance to Strawberry type.

        Args:
            cls: The class to instantiate
            instance: Django model instance

        Returns:
            An instance of the Strawberry type
        """
        # Convert Django model instance to a dictionary of fields
        data = {}
        for field in instance._meta.fields:
            data[field.name] = getattr(instance, field.name)

        # from_dict can return None, but we know we have valid data from Django model
        result = cls.from_dict(data)
        if result is None:
            raise ValueError(
                f"Failed to convert Django model {instance} to Strawberry type {cls}"
            )
        return result

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> Optional[T]:
        """Create an instance from a dictionary.

        Args:
            cls: The class to instantiate
            data: Dictionary containing the data

        Returns:
            An instance of the Strawberry type or None if data is invalid
        """
        if not data:
            return None
        try:
            return cast(T, cls(**data))
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def from_django_list(cls: Type[T], queryset: QuerySet[M]) -> List[T]:
        """Convert a Django QuerySet to a list of Strawberry types.

        Args:
            cls: The class to instantiate
            queryset: Django QuerySet to convert

        Returns:
            List of Strawberry types
        """
        return [cls.from_django(instance) for instance in queryset]
