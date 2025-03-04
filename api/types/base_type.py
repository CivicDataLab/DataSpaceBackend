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
    def from_django_list(
        cls: Type[T], instances: Union[Sequence[M], QuerySet[M, Any]]
    ) -> List[T]:
        """Convert a list of Django model instances to Strawberry types.

        Args:
            cls: The class to instantiate
            instances: List or QuerySet of Django model instances

        Returns:
            List of Strawberry type instances
        """
        return [cls.from_django(instance) for instance in instances]
