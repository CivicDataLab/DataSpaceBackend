"""GraphQL type for prompt resource details."""

from typing import Optional

import strawberry
from strawberry.enum import EnumType

from api.utils.enums import PromptFormat

# Create the enum for GraphQL schema
prompt_format_enum: EnumType = strawberry.enum(PromptFormat)  # type: ignore


@strawberry.type
class TypePromptResourceDetails:
    """Prompt-specific fields for a resource/file."""

    prompt_format: Optional[prompt_format_enum]
    has_system_prompt: bool
    has_example_responses: bool
    avg_prompt_length: Optional[int]
    prompt_count: Optional[int]
