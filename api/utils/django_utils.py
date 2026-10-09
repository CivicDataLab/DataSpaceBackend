from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Field, Model, QuerySet

T = TypeVar("T", bound=models.Model)
GraphQLType = TypeVar("GraphQLType")


def retry_on_slug_collision(
    save_fn: Callable[[], None],
    disambiguate: Callable[[int], None],
    max_attempts: int = 5,
) -> None:
    """Retry a model save that failed on a title/slug uniqueness collision.

    Auto-generated titles like "New dataset 17 Sep 2026 - 09:43:04" only have
    one-second resolution, so two records created in the same second collide
    on the unique slug (and, for models where title is also unique, on title
    too). On each retry `disambiguate(attempt)` should mutate the instance's
    title/slug to a new candidate (e.g. append " (n)") before `save_fn` is
    called again. Each attempt runs in its own savepoint so a failed attempt
    doesn't poison the caller's outer transaction.

    ponytail: catches ValidationError broadly (not just the title/slug keys)
    so an unrelated validation failure retries pointlessly a few times before
    surfacing the same error - upgrade to inspecting message_dict if that
    noise ever matters.
    """
    attempt = 0
    while True:
        try:
            with transaction.atomic():
                save_fn()
            return
        except (IntegrityError, ValidationError):
            attempt += 1
            if attempt >= max_attempts:
                raise
            disambiguate(attempt)


def get_graphql_type_fields_name(type_: Type[GraphQLType]) -> Dict[str, Any]:
    """Get field names from a GraphQL type."""
    fields = type_.__dict__.get("__dataclass_fields__", {})
    return cast(Dict[str, Any], fields.keys())


def convert_to_graphql_type(
    db_model_object: Model, graphql_type: Type[GraphQLType]
) -> GraphQLType:
    """Convert a Django model object to a GraphQL type."""
    fields = get_graphql_type_fields_name(graphql_type)
    field_values = {
        field: getattr(db_model_object, field)
        for field in fields
        if hasattr(db_model_object, field)
    }
    return cast(GraphQLType, graphql_type(**field_values))
