from typing import Any, Dict, List, Optional, Type, TypeVar, Union, cast

from django.db import models
from django.db.models import Field, Model, QuerySet

T = TypeVar("T", bound=models.Model)
GraphQLType = TypeVar("GraphQLType")


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
