from typing import Any, Dict, List, Optional, Union, cast

from django.db import IntegrityError
from graphql import GraphQLError
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from api.utils.error_handlers import ErrorDictType, format_integrity_error


class ErrorFormatterExtension(Extension):  # type: ignore[misc,valid-type]
    def process_errors(
        self, errors: List[GraphQLError], execution_context: ExecutionContext
    ) -> List[GraphQLError]:
        formatted_errors = []
        for error in errors:
            original = getattr(error, "original_error", error)

            if isinstance(original, IntegrityError):
                error_data = format_integrity_error(original)
                if "field_errors" in error_data:
                    field_errors = cast(
                        Dict[str, List[str]], error_data["field_errors"]
                    )
                    formatted_errors.append(
                        GraphQLError(
                            message=next(iter(field_errors.values()))[0],
                            path=error.path,
                            extensions={"field_errors": field_errors},
                        )
                    )
                else:
                    non_field_errors = cast(List[str], error_data["non_field_errors"])
                    formatted_errors.append(
                        GraphQLError(
                            message=non_field_errors[0],
                            path=error.path,
                            extensions={"non_field_errors": non_field_errors},
                        )
                    )
            else:
                formatted_errors.append(error)

        return formatted_errors
