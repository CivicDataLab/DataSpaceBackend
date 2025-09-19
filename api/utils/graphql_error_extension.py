from typing import Any, Dict, List, Optional, Union, cast

from django.db import DataError, IntegrityError
from graphql import GraphQLError
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from api.utils.error_handlers import (
    ErrorDictType,
    FieldErrors,
    NonFieldErrors,
    format_data_error,
    format_integrity_error,
    is_field_errors,
    is_non_field_errors,
)


class ErrorFormatterExtension(Extension):  # type: ignore[misc,valid-type]
    def process_errors(
        self, errors: List[GraphQLError], execution_context: ExecutionContext
    ) -> List[GraphQLError]:
        formatted_errors = []
        for error in errors:
            original = getattr(error, "original_error", error)

            if isinstance(original, (DataError, IntegrityError)):
                error_data = (
                    format_data_error(original)
                    if isinstance(original, DataError)
                    else format_integrity_error(original)
                )
                if is_field_errors(error_data):
                    field_errors = error_data["field_errors"]
                    if not field_errors:
                        formatted_errors.append(error)
                        continue
                    # Get the first error message safely
                    first_field = next(iter(field_errors.keys()))
                    first_message = (
                        field_errors[first_field][0]
                        if field_errors[first_field]
                        else "Field validation error"
                    )
                    formatted_errors.append(
                        GraphQLError(
                            message=first_message,
                            path=error.path,
                            extensions={"field_errors": field_errors},
                        )
                    )
                elif is_non_field_errors(error_data):
                    non_field_errors = error_data["non_field_errors"]
                    if not non_field_errors:
                        formatted_errors.append(error)
                        continue
                    # Get the first error message safely
                    first_message = (
                        non_field_errors[0]
                        if non_field_errors
                        else "Non-field validation error"
                    )
                    formatted_errors.append(
                        GraphQLError(
                            message=first_message,
                            path=error.path,
                            extensions={"non_field_errors": non_field_errors},
                        )
                    )
            else:
                formatted_errors.append(error)

        return formatted_errors
