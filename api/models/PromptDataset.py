"""PromptDataset model - extends Dataset with prompt-specific fields."""

from django.db import models

from api.models.Dataset import Dataset
from api.utils.enums import DatasetType, PromptDomain, PromptFormat, PromptTaskType


class PromptDataset(Dataset):
    """
    PromptDataset extends Dataset with prompt-specific fields.

    Uses Django multi-table inheritance - PromptDataset has all fields
    from Dataset plus additional prompt-specific fields. The parent
    Dataset is automatically created and linked via a OneToOne relationship.

    This means PromptDataset:
    - Has all Dataset fields (title, description, tags, sectors, etc.)
    - Can have DatasetMetadata entries (via inherited relationship)
    - Can have Resources (prompt files instead of data files)
    - Has additional prompt-specific fields below
    """

    # Prompt task type (e.g., text generation, classification, etc.)
    task_type = models.CharField(
        max_length=100,
        choices=PromptTaskType.choices,
        blank=True,
        null=True,
    )

    # Target language(s) for the prompts
    target_languages = models.JSONField(
        blank=True,
        null=True,
        help_text="List of target languages for the prompts (e.g., ['en', 'hi', 'ta'])",
    )

    # Domain/category of prompts
    domain = models.CharField(
        max_length=200,
        choices=PromptDomain.choices,
        blank=True,
        null=True,
        help_text="Domain or category (e.g., healthcare, education, legal)",
    )

    # Target AI model types
    target_model_types = models.JSONField(
        blank=True,
        null=True,
        help_text="List of AI model types these prompts are designed for (e.g., ['GPT', 'LLAMA'])",
    )

    # Prompt format/template information
    prompt_format = models.CharField(
        max_length=100,
        choices=PromptFormat.choices,
        blank=True,
        null=True,
        help_text="Format of prompts (e.g., instruction, chat, completion)",
    )

    # Whether prompts include system instructions
    has_system_prompt = models.BooleanField(
        default=False,
        help_text="Whether the prompts include system-level instructions",
    )

    # Whether prompts include example responses
    has_example_responses = models.BooleanField(
        default=False,
        help_text="Whether the prompts include example/expected responses",
    )

    # Average prompt length (for filtering/search)
    avg_prompt_length = models.IntegerField(
        blank=True,
        null=True,
        help_text="Average character length of prompts in this dataset",
    )

    # Number of prompts in the dataset
    prompt_count = models.IntegerField(
        blank=True,
        null=True,
        help_text="Total number of prompts in this dataset",
    )

    # Use case description
    use_case = models.TextField(
        blank=True,
        null=True,
        help_text="Description of intended use cases for these prompts",
    )

    # Evaluation criteria or metrics
    evaluation_criteria = models.JSONField(
        blank=True,
        null=True,
        help_text="Criteria or metrics for evaluating prompt effectiveness",
    )

    def save(self, *args, **kwargs):
        # Ensure dataset_type is always PROMPT for PromptDataset
        self.dataset_type = DatasetType.PROMPT
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"PromptDataset: {self.title}"

    class Meta:
        db_table = "prompt_dataset"
        verbose_name = "Prompt Dataset"
        verbose_name_plural = "Prompt Datasets"
