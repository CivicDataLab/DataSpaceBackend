from typing import Any, Dict, List, Optional, Union, cast

from django.db import IntegrityError
from graphql import GraphQLError
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from api.utils.error_handlers import ErrorDictType, format_integrity_error


class ErrorFormatterExtension(Extension):  # type: ignore[misc,valid-type]
    def format_errors(self, errors: List[GraphQLError]) -> List[GraphQLError]:
        return [self.format_error(error) for error in errors]

    def format_error(self, error: GraphQLError) -> GraphQLError:
        original = getattr(error, "original_error", error)

        if isinstance(original, IntegrityError):
            error_data = format_integrity_error(original)
            if "field_errors" in error_data:
                field_errors = cast(Dict[str, List[str]], error_data["field_errors"])
                # Return a properly formatted GraphQL error
                return GraphQLError(
                    message=next(iter(field_errors.values()))[0],
                    path=error.path,
                    extensions={"field_errors": field_errors},
                )
            else:
                non_field_errors = cast(List[str], error_data["non_field_errors"])
                return GraphQLError(
                    message=non_field_errors[0],
                    path=error.path,
                    extensions={"non_field_errors": non_field_errors},
                )

        # For other errors, return the original error
        return error
