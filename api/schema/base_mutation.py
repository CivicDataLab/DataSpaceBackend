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
from django.db import DataError, IntegrityError
from strawberry.field import StrawberryField  # type: ignore
from strawberry.types import Info

from api.utils.error_handlers import (
    convert_error_dict,
    format_data_error,
    format_integrity_error,
    format_validation_error,
)

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
        formatted_field_errors = []
        if isinstance(field_errors, dict):
            for field, messages in field_errors.items():
                # Handle case where messages might be a string or already a list
                if isinstance(messages, str):
                    message_list = [messages]
                elif isinstance(messages, list):
                    # Handle potential string representation of list
                    message_list = (
                        [msg.strip("[]\"' ") for msg in messages]
                        if len(messages) == 1 and messages[0].startswith("[")
                        else messages
                    )
                else:
                    message_list = [str(messages)]

                formatted_field_errors.append(
                    FieldError(field=field, messages=message_list)
                )

        # Handle non-field errors
        if isinstance(non_field_errors, list):
            # Clean up any string representation of lists
            cleaned_errors = (
                [err.strip("[]\"' ") for err in non_field_errors]
                if len(non_field_errors) == 1 and non_field_errors[0].startswith("[")
                else non_field_errors
            )
        else:
            cleaned_errors = [str(non_field_errors)]

        return GraphQLValidationError(
            field_errors=formatted_field_errors or None,
            non_field_errors=cleaned_errors or None,
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

                except (DataError, IntegrityError) as e:
                    error_data = (
                        format_data_error(e)
                        if isinstance(e, DataError)
                        else format_integrity_error(e)
                    )
                    return MutationResponse.error_response(
                        BaseMutation.format_errors(convert_error_dict(error_data))
                    )
                except (DjangoValidationError, PermissionDenied) as e:
                    validation_errors = getattr(info.context, "validation_errors", None)
                    if validation_errors:
                        errors = BaseMutation.format_errors(validation_errors)
                    elif isinstance(e, DjangoValidationError):
                        # Format validation errors with field names
                        error_data = format_validation_error(e)
                        errors = BaseMutation.format_errors(
                            convert_error_dict(error_data)
                        )
                    else:
                        errors = GraphQLValidationError.from_message(str(e))
                    return MutationResponse.error_response(errors)
                except Exception as e:
                    errors = GraphQLValidationError.from_message(str(e))
                    return MutationResponse.error_response(errors)

            return wrapper

        return decorator
