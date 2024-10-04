from enum import Enum
from typing import List

import strawberry
import strawberry_django

from api.models import Metadata


@strawberry.enum
class ValidatorType(Enum):
    REGEX = "regex_validator"
    RANGE = "range_validator"
    MIN_LENGTH = "min_length_validator"


@strawberry_django.filter(Metadata)
class MetadataFilter:
    model: str
    enabled: bool


@strawberry_django.type(Metadata, fields="__all__", filters=MetadataFilter)
class TypeMetadata:
    validator: List[ValidatorType]
