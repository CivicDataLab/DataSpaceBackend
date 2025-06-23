from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, cast

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from api.utils.enums import (
    MetadataDataTypes,
    MetadataModels,
    MetadataStandards,
    MetadataTypes,
)
from api.utils.metadata_validators import VALIDATOR_MAP


class MetadataType(Protocol):
    id: int
    label: str
    data_type: str
    type: str
    options: Optional[List[str]]
    validator: List[str]
    validator_options: Any


class BaseMetadata(models.Model):
    """Base class for all metadata models."""

    id = models.AutoField(primary_key=True)
    metadata_item = models.ForeignKey(
        "api.Metadata", on_delete=models.CASCADE, null=False, blank=False
    )
    value = models.CharField(max_length=1000, unique=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["metadata_item__label"]

    def clean(self) -> None:
        """
        Custom validation logic to validate the value against metadata_item's options.
        """
        metadata = cast(MetadataType, self.metadata_item)
        value = str(self.value)
        self._validate_data_type(metadata, value)
        self._apply_custom_validators(metadata, value)

    def _apply_custom_validators(self, metadata: MetadataType, value: str) -> None:
        """
        Apply user-selected custom validators.
        """
        selected_validators: List[str] = getattr(metadata, "validator", [])

        for validator_name in selected_validators:
            validator = VALIDATOR_MAP.get(validator_name)

            if validator:
                if validator_name == "regex_validator":
                    pattern = getattr(metadata, "validator_options", "")
                    validator(value, pattern)  # type: ignore
                else:
                    validator(value)  # type: ignore
            else:
                raise ValidationError(f"Unknown validator: {validator_name}")

    def _validate_data_type(self, metadata: MetadataType, value: str) -> None:
        validation_methods: Dict[str, Callable[[MetadataType, str], None]] = {
            MetadataDataTypes.STRING: self._validate_string,
            MetadataDataTypes.NUMBER: self._validate_number,
            MetadataDataTypes.DATE: self._validate_date,
            MetadataDataTypes.URL: self._validate_url,
            MetadataDataTypes.SELECT: self._validate_select,
            MetadataDataTypes.MULTISELECT: self._validate_multiselect,
        }
        # Get the corresponding validation method based on the data_type
        data_type: Optional[str] = getattr(metadata, "data_type", None)
        validate_method = validation_methods.get(data_type) if data_type else None

        metadata_type = getattr(metadata, "type", None)
        if not value and metadata_type is MetadataTypes.REQUIRED:
            raise ValidationError(
                f"Required value not sent for: {getattr(metadata, 'label', '')}"
            )

        if validate_method:
            try:
                validate_method(metadata, value)
            except ValidationError as e:
                # if metadata_type is MetadataTypes.REQUIRED:
                raise e
                # else:
                #     # Set empty value for non-required fields with validation errors
                #     self.value = ""
        else:
            raise ValidationError(f"Unknown data type: {data_type}")

    def _validate_string(self, metadata: MetadataType, value: str) -> None:
        """Validate string type."""
        if not isinstance(value, str):
            raise ValidationError(
                f"Value for '{getattr(metadata, 'label', '')}' must be a string."
            )

    def _validate_number(self, metadata: MetadataType, value: str) -> None:
        """Validate number type."""
        try:
            float(value)
        except ValueError:
            raise ValidationError(
                f"Value for '{getattr(metadata, 'label', '')}' must be a valid number."
            )

    def _validate_select(self, metadata: MetadataType, value: str) -> None:
        """Validate singleselect type."""
        options = getattr(metadata, "options", [])
        if value not in options:
            raise ValidationError(
                f"Invalid value: '{value}' for '{getattr(metadata, 'label', '')}'. Must be one of {options}."
            )

    def _validate_multiselect(self, metadata: MetadataType, value: str) -> None:
        """Validate multiselect type."""
        options = getattr(metadata, "options", [])
        selected_values = [v.strip() for v in value.split(",")]
        invalid_values = [v for v in selected_values if v not in options]
        if invalid_values:
            raise ValidationError(
                f"Invalid values: {', '.join(invalid_values)} for '{getattr(metadata, 'label', '')}'. Must be one of {options}."
            )

    def _validate_date(self, metadata: MetadataType, value: str) -> None:
        """Validate date type."""
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValidationError(
                f"Value for '{getattr(metadata, 'label', '')}' must be a valid date in YYYY-MM-DD format."
            )

    def _validate_url(self, metadata: MetadataType, value: str) -> None:
        """Validate URL type."""
        validator = URLValidator()
        try:
            validator(value)
        except ValidationError:
            raise ValidationError(
                f"Value for '{getattr(metadata, 'label', '')}' must be a valid URL."
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Override save to run validation before saving.
        """
        self.clean()
        super().save(*args, **kwargs)


class Metadata(models.Model):
    id = models.AutoField(primary_key=True)
    label = models.CharField(max_length=75, unique=False)
    data_standard = models.CharField(
        max_length=50,
        choices=MetadataStandards.choices,
        blank=True,
        unique=False,
        null=True,
    )
    urn = models.CharField(max_length=175, unique=True, blank=True)
    data_type = models.CharField(
        max_length=50, choices=MetadataDataTypes.choices, blank=False, unique=False
    )
    options = models.JSONField(blank=True, null=True)  # for select and multiselect
    validator = models.JSONField(blank=True, default=list)  # predefined set
    validator_options = models.JSONField(
        blank=True, null=True
    )  # options for validation
    type = models.CharField(
        max_length=50, choices=MetadataTypes.choices, blank=False, unique=False
    )
    model = models.CharField(
        max_length=50, choices=MetadataModels.choices, blank=False, unique=False
    )
    enabled = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.label} ({self.data_type})"

    class Meta:
        db_table = "metadata"
        ordering = ["label"]
