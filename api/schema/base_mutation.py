from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
)

import strawberry
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from strawberry.field import StrawberryField  # type: ignore
from strawberry.types import Info

from api.utils.error_handlers import ErrorDictType, format_integrity_error

ActivityData = Dict[str, Any]
ActivityDataGetter = Callable[[Any, Dict[str, Any]], ActivityData]


@strawberry.type
class FieldError:
    field: str
    messages: List[str]


@strawberry.type
class GraphQLValidationError:
    field_errors: Optional[List[FieldError]] = None
    non_field_errors: Optional[List[str]] = None

    @classmethod
    def from_message(cls, message: str) -> "GraphQLValidationError":
        return cls(non_field_errors=[message])


T = TypeVar("T")


@strawberry.type
class MutationResponse(Generic[T]):
    success: bool = True
    errors: Optional[GraphQLValidationError] = None
    data: Optional[T] = None

    @classmethod
    def success_response(cls, data: T) -> "MutationResponse[T]":
        return cls(success=True, data=data)

    @classmethod
    def error_response(cls, error: GraphQLValidationError) -> "MutationResponse[T]":
        return cls(success=False, errors=error)


class BaseMutation(Generic[T]):
    @staticmethod
    def format_errors(
        validation_errors: Optional[Dict[str, Union[Dict[str, List[str]], List[str]]]],
    ) -> GraphQLValidationError:
        if not validation_errors:
            return GraphQLValidationError()

        field_errors = validation_errors.get("field_errors", {})
        non_field_errors = validation_errors.get("non_field_errors", [])

        # Convert dict field errors to list of FieldError objects
        formatted_field_errors = (
            [
                FieldError(field=field, messages=messages)
                for field, messages in field_errors.items()
            ]
            if isinstance(field_errors, dict)
            else []
        )

        return GraphQLValidationError(
            field_errors=formatted_field_errors or None,
            non_field_errors=(
                non_field_errors if isinstance(non_field_errors, list) else None
            ),
        )

    @classmethod
    def mutation(
        cls,
        *,
        permission_classes: Optional[List[Type]] = None,
        track_activity: Optional[Dict[str, Union[str, ActivityDataGetter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to handle permissions, error handling, and activity tracking.
        This should be applied AFTER @strawberry.mutation to properly handle errors.
        """

        def decorator(
            func: Union[Callable[..., Any], "StrawberryField"]
        ) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(
                cls: Any, info: Info, *args: Any, **kwargs: Any
            ) -> MutationResponse[T]:
                try:
                    # Check permissions if provided
                    if permission_classes:
                        for permission_class in permission_classes:
                            permission = permission_class()
                            if not permission.has_permission(None, info, **kwargs):
                                raise PermissionDenied(
                                    permission.message
                                    or f"Permission denied: {permission_class.__name__}"
                                )

                    # Execute the mutation
                    result = func(cls, info, *args, **kwargs)

                    # Handle activity tracking if configured
                    if track_activity and hasattr(info.context, "track_activity"):
                        data_getter = track_activity.get("get_data")
                        verb = track_activity.get("verb", "")

                        if data_getter and callable(data_getter):
                            activity_data = data_getter(result, **kwargs)  # type: ignore[call-arg]
                            info.context.track_activity(verb=verb, data=activity_data)  # type: ignore[call-arg]

                    # If the result is already a MutationResponse, return it
                    if isinstance(result, MutationResponse):
                        return result

                    # Otherwise, wrap the result in a MutationResponse
                    return MutationResponse.success_response(result)

                except IntegrityError as e:
                    error_data = format_integrity_error(e)
                    if "field_errors" in error_data:
                        return MutationResponse.error_response(
                            BaseMutation.format_errors(
                                {"field_errors": error_data["field_errors"]}
                            )
                        )
                    else:
                        return MutationResponse.error_response(
                            BaseMutation.format_errors(
                                {"non_field_errors": error_data["non_field_errors"]}
                            )
                        )

                except (DjangoValidationError, PermissionDenied) as e:
                    # Get validation errors from context if available
                    validation_errors = getattr(info.context, "validation_errors", None)
                    if validation_errors:
                        errors = BaseMutation.format_errors(validation_errors)
                    else:
                        errors = GraphQLValidationError.from_message(str(e))
                    return MutationResponse.error_response(errors)

            return wrapper

        return decorator
