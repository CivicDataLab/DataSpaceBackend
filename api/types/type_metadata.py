from enum import Enum
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Metadata
from api.types.base_type import BaseType
from api.utils.enums import MetadataModels

metadata_models = strawberry.enum(MetadataModels)


@strawberry.enum
class ValidatorType(Enum):
    """Type of validator."""

    REGEX = "regex_validator"
    RANGE = "range_validator"
    MIN_LENGTH = "min_length_validator"


@strawberry_django.filter(Metadata)
class MetadataFilter:
    """Filter for metadata."""

    model: metadata_models
    enabled: bool


@strawberry_django.type(Metadata, fields="__all__", filters=MetadataFilter)
class TypeMetadata(BaseType):
    """Type for metadata."""

    id: auto
    label: auto
    model: metadata_models
    type: auto
    enabled: auto
    validator: List[ValidatorType]
    created: auto
    modified: auto
