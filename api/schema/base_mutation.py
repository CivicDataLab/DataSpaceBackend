from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypedDict,
    TypeVar,
    Union,
    cast,
    get_args,
)

import strawberry
import structlog
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError, IntegrityError
from django.db.models import Model
from strawberry.types import Info

from api.utils.error_handlers import (
    convert_error_dict,
    format_data_error,
    format_integrity_error,
    format_validation_error,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.activity import record_activity

logger = structlog.getLogger(__name__)

# Type aliases
ActivityData = Dict[str, Any]
ActivityDataGetter = Callable[[Any, Dict[str, Any]], ActivityData]  # type: ignore

# Generic type for mutation responses
T = TypeVar("T")


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


@strawberry.type
class MutationResponse(Generic[T]):  # type: ignore
    success: bool = True
    errors: Optional[GraphQLValidationError] = None
    data: Optional[T] = None

    @classmethod
    def success_response(cls, data: Any) -> "MutationResponse[T]":  # type: ignore
        return cls(success=True, data=data)

    @classmethod
    def error_response(
        cls, error: GraphQLValidationError
    ) -> "MutationResponse[T]":  # type: ignore
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
        track_activity: Optional[Dict[str, Any]] = None,
        trace_name: Optional[str] = None,
        trace_attributes: Optional[Dict[str, str]] = None,
    ) -> Callable[[Any], Any]:  # type: ignore
        """Decorator to handle permissions, error handling, activity tracking, and tracing.
        This should be applied AFTER @strawberry.mutation to properly handle errors.

        Args:
            permission_classes: List of permission classes to check
            track_activity: Activity tracking configuration
            trace_name: Optional name for the trace span
            trace_attributes: Optional attributes to add to the trace span
        """

        def decorator(func: Any) -> Any:  # type: ignore
            @wraps(func)
            @trace_resolver(
                name=trace_name or func.__name__,
                attributes={
                    "component": "mutation",
                    "operation": "mutation",
                    **(trace_attributes or {}),
                },
            )
            def wrapper(
                cls: Any, info: Info, *args: Any, **kwargs: Any
            ) -> MutationResponse[T]:  # type: ignore
                try:
                    # Check permissions if provided
                    if permission_classes:
                        for permission_class in permission_classes:
                            permission = permission_class()
                            if not permission.has_permission(
                                info.context.user, info, **kwargs
                            ):
                                raise PermissionDenied(
                                    permission.message
                                    or f"Permission denied: {permission_class.__name__}"
                                )

                    # Execute the mutation
                    result = func(cls, info, *args, **kwargs)  # type: ignore

                    # Track activity if configured
                    if (
                        track_activity
                        and isinstance(track_activity, dict)
                        and "verb" in track_activity
                    ):
                        verb: str = track_activity["verb"]
                        get_data = track_activity.get("get_data")
                        if verb:
                            # Get data from getter if provided
                            data_getter = get_data if get_data else lambda x, **k: {}
                            try:
                                action_data = (
                                    data_getter(result.data, **kwargs)
                                    if result.data
                                    else {}
                                )
                            except Exception:
                                action_data = {}

                            # Record activity with data
                            if result.data and isinstance(result.data, Model):
                                record_activity(
                                    actor=info.context.user,
                                    verb=verb,
                                    action_object=result.data,  # type: ignore
                                    request=info.context,
                                    **action_data,
                                )

                    # Handle the mutation result
                    if result is None:
                        return MutationResponse.success_response(None)  # type: ignore
                    elif isinstance(result, MutationResponse):
                        return result
                    else:
                        return MutationResponse.success_response(result)  # type: ignore

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
                    # Log the error but don't expose internal details
                    error_message = "An unexpected error occurred"
                    logger.error("mutation_failed", error=str(e))
                    errors = GraphQLValidationError.from_message(error_message)
                    return MutationResponse.error_response(errors)  # type: ignore

            return cast(Any, wrapper)  # type: ignore

        return cast(Any, decorator)  # type: ignore
