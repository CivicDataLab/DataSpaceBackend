"""GraphQL type for PromptDataset."""

import uuid
from datetime import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models.PromptDataset import PromptDataset
from api.types.base_type import BaseType
from api.types.type_dataset import TypeDataset
from api.utils.enums import (
    PromptDomain,
    PromptTaskType,
    TargetLanguage,
    TargetModelType,
)

prompt_task_type_enum: EnumType = strawberry.enum(PromptTaskType)  # type: ignore
prompt_domain_enum: EnumType = strawberry.enum(PromptDomain)  # type: ignore
target_language_enum: EnumType = strawberry.enum(TargetLanguage)  # type: ignore
target_model_type_enum: EnumType = strawberry.enum(TargetModelType)  # type: ignore


@strawberry_django.type(
    PromptDataset,
    fields="__all__",
)
class TypePromptDataset(TypeDataset):
    """
    GraphQL type for PromptDataset.

    Extends TypeDataset with prompt-specific fields.
    Inherits all Dataset fields plus adds prompt-specific ones.
    """

    # Dataset-level prompt fields
    task_type: Optional[prompt_task_type_enum]
    target_languages: Optional[List[target_language_enum]]
    domain: Optional[prompt_domain_enum]
    target_model_types: Optional[List[target_model_type_enum]]
    evaluation_criteria: Optional[strawberry.scalars.JSON]
