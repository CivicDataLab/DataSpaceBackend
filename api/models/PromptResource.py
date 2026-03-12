"""PromptResource model - extends Resource with prompt-specific fields."""

from django.db import models

from api.models.Resource import Resource
from api.utils.enums import PromptFormat


class PromptResource(models.Model):
    """
    PromptResource adds prompt-specific metadata to a Resource.

    This is a OneToOne extension of Resource (not multi-table inheritance)
    to store prompt file-specific fields like format, system prompt presence, etc.

    """

    resource = models.OneToOneField(
        Resource,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="prompt_details",
    )

    # Prompt format/template information
    prompt_format = models.CharField(
        max_length=100,
        choices=PromptFormat.choices,
        blank=True,
        null=True,
        help_text="Format of prompts in this file (e.g., instruction, chat, completion)",
    )

    # Whether prompts include system instructions
    has_system_prompt = models.BooleanField(
        default=False,
        help_text="Whether the prompts in this file include system-level instructions",
    )

    # Whether prompts include example responses
    has_example_responses = models.BooleanField(
        default=False,
        help_text="Whether the prompts in this file include example/expected responses",
    )

    # Average prompt length (for filtering/search)
    avg_prompt_length = models.IntegerField(
        blank=True,
        null=True,
        help_text="Average character length of prompts in this file",
    )

    # Number of prompts in this file
    prompt_count = models.IntegerField(
        blank=True,
        null=True,
        help_text="Total number of prompts in this file",
    )

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"PromptResource: {self.resource.name}"

    class Meta:
        db_table = "prompt_resource"
        verbose_name = "Prompt Resource"
        verbose_name_plural = "Prompt Resources"
