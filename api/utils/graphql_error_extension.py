from typing import Any, Dict, List, Optional, Union, cast

from django.db import IntegrityError
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from api.utils.error_handlers import ErrorDictType, format_integrity_error


class ErrorFormatterExtension(Extension):  # type: ignore[misc,valid-type]
    def on_execute(self) -> None:
        # Register error formatter
        self.execution_context.error_formatters.append(self.format_error)

    def format_error(
        self, error: Any, path: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        # Format the error into a GraphQL-compliant structure
        if isinstance(error, Exception):
            original = (
                error.original_error if hasattr(error, "original_error") else error
            )

            if isinstance(original, IntegrityError):
                error_data = format_integrity_error(original)
                if "field_errors" in error_data:
                    field_errors = cast(
                        Dict[str, List[str]], error_data["field_errors"]
                    )
                    # Return a properly formatted GraphQL error
                    return {
                        "message": next(iter(field_errors.values()))[0],
                        "path": path,
                        "extensions": {"field_errors": field_errors},
                    }
                else:
                    non_field_errors = cast(List[str], error_data["non_field_errors"])
                    return {
                        "message": non_field_errors[0],
                        "path": path,
                        "extensions": {"non_field_errors": non_field_errors},
                    }

        # For other errors, return the default format
        return {
            "message": str(error),
            "path": path,
        }
