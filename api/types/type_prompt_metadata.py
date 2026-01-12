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
from api.utils.enums import PromptTaskType

prompt_task_type_enum: EnumType = strawberry.enum(PromptTaskType)  # type: ignore


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

    # Prompt-specific fields
    task_type: Optional[prompt_task_type_enum]
    target_languages: Optional[List[str]]
    domain: Optional[str]
    target_model_types: Optional[List[str]]
    prompt_format: Optional[str]
    has_system_prompt: bool
    has_example_responses: bool
    avg_prompt_length: Optional[int]
    prompt_count: Optional[int]
    use_case: Optional[str]
    evaluation_criteria: Optional[strawberry.scalars.JSON]


# Keep TypePromptMetadata as an alias for backward compatibility in nested queries
@strawberry.type
class TypePromptMetadata:
    """Prompt-specific metadata fields (for embedding in TypeDataset)."""

    task_type: Optional[prompt_task_type_enum]
    target_languages: Optional[List[str]]
    domain: Optional[str]
    target_model_types: Optional[List[str]]
    prompt_format: Optional[str]
    has_system_prompt: bool
    has_example_responses: bool
    avg_prompt_length: Optional[int]
    prompt_count: Optional[int]
    use_case: Optional[str]
    evaluation_criteria: Optional[strawberry.scalars.JSON]
