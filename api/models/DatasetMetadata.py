from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from api.enums import MetadataDataTypes
from api.metadata_validators import VALIDATOR_MAP
from api.models import Dataset, Metadata


class DatasetMetadata(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False, blank=False, related_name="metadata")
    metadata_item = models.ForeignKey(Metadata, on_delete=models.CASCADE, null=False, blank=False, )
    value = models.CharField(max_length=1000, unique=False)

    def clean(self):
        """
        Custom validation logic to validate the value against metadata_item's options.
        """
        metadata = self.metadata_item
        options = metadata.options
        value = self.value
        self._validate_data_type(metadata, value)
        self._apply_custom_validators(metadata, value)

    def _apply_custom_validators(self, metadata, value):
        """
        Apply user-selected custom validators.
        """
        selected_validators = metadata.validator  # Assuming this is a list of validator names

        for validator_name in selected_validators:
            validator = VALIDATOR_MAP.get(validator_name, None)

            if validator:
                if validator_name == "regex_validator":
                    pattern = metadata.validator_options  # Example: storing pattern in options
                    validator(value, pattern)
                else:
                    validator(value)
            else:
                raise ValidationError(f"Unknown validator: {validator_name}")

    def _validate_data_type(self, metadata, value):
        validation_methods = {
            MetadataDataTypes.STRING: self._validate_string,
            MetadataDataTypes.NUMBER: self._validate_number,
            MetadataDataTypes.SELECT: self._validate_select,
            MetadataDataTypes.MULTISELECT: self._validate_multiselect,
            MetadataDataTypes.DATE: self._validate_date,
            MetadataDataTypes.URL: self._validate_url,
        }
        # Get the corresponding validation method based on the data_type
        validate_method = validation_methods.get(metadata.data_type, None)
        if validate_method:
            validate_method(metadata, value)
        else:
            raise ValidationError(f"Unsupported metadata type: {metadata.data_type}")

    def _validate_string(self, metadata, value):
        """Validate string type."""
        if not isinstance(value, str):
            raise ValidationError(f"Value for '{metadata.label}' must be a string.")

    def _validate_number(self, metadata, value):
        """Validate number type."""
        try:
            float(value)
        except ValueError:
            raise ValidationError(f"Value for '{metadata.label}' must be a valid number.")

    def _validate_select(self, metadata, value):
        """Validate singleselect type."""
        if value not in metadata.options:
            raise ValidationError(
                f"Invalid value: '{value}' for '{metadata.label}'. Must be one of {metadata.options}.")

    def _validate_multiselect(self, metadata, value):
        """Validate multiselect type."""
        selected_values = [v.strip() for v in value.split(",")]
        invalid_values = [v for v in selected_values if v not in metadata.options]
        if invalid_values:
            raise ValidationError(f"Invalid values: {', '.join(invalid_values)}. Must be one of {metadata.options}.")

    def _validate_date(self, metadata, value):
        """Validate date type."""
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValidationError(f"Value for '{metadata.label}' must be a valid date in YYYY-MM-DD format.")

    def _validate_url(self, metadata, value):
        """Validate URL type."""
        validator = URLValidator()
        try:
            validator(value)
        except ValidationError:
            raise ValidationError(f"Value for '{metadata.label}' must be a valid URL.")

    def save(self, *args, **kwargs):
        """
        Override save to apply validation before saving.
        """
        try:
            self.clean()  # Call custom clean method to trigger validation
            super(DatasetMetadata, self).save(*args, **kwargs)
        except ValidationError as e:
            raise Exception(f"Something went wrong while saving metadata with error {e.message}")

    def __str__(self):
        return f"{self.dataset.title} - {self.metadata_item.label}: {self.value}"
