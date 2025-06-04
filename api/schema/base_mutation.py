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
from strawberry.types import Info

from api.utils.error_handlers import ErrorDictType, handle_django_errors

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


class BaseMutation:
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

    @staticmethod
    def mutation(
        *,
        permission_classes: Optional[List[Type]] = None,
        track_activity: Optional[Dict[str, Union[str, ActivityDataGetter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            @handle_django_errors
            def wrapper(cls: Any, info: Info, *args: Any, **kwargs: Any) -> Any:
                try:
                    # Check permissions if provided
                    if permission_classes:
                        for permission_class in permission_classes:
                            if not permission_class.has_permission(info.context):
                                raise PermissionDenied(
                                    f"Permission denied: {permission_class.__name__}"
                                )

                    # Get the return type annotation which should be MutationResponse[T]
                    return_type = func.__annotations__.get("return")
                    response_type = get_args(return_type)[0] if return_type else None

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
                    if return_type and issubclass(return_type, MutationResponse):
                        return return_type.success_response(result)  # type: ignore[call-arg]

                except (DjangoValidationError, IntegrityError, PermissionDenied) as e:
                    # Get validation errors from context if available
                    validation_errors = getattr(info.context, "validation_errors", None)
                    if validation_errors:
                        errors = BaseMutation.format_errors(validation_errors)
                    else:
                        errors = GraphQLValidationError.from_message(str(e))

                    # Get the return type annotation
                    return_type = func.__annotations__.get("return")
                    if return_type and issubclass(return_type, MutationResponse):
                        return return_type.error_response(errors)  # type: ignore[call-arg]

            return wrapper

        return decorator
