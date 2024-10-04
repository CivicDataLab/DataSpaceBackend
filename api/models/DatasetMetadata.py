from django.core.exceptions import ValidationError
from django.db import models

from api.enums import MetadataDataTypes
from api.models import Dataset, Metadata


class DatasetMetadata(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False, blank=False, related_name="metadata")
    metadata_item = models.ForeignKey(Metadata, on_delete=models.CASCADE, null=False, blank=False,)
    value = models.CharField(max_length=1000, unique=False)

    def clean(self):
        """
        Custom validation logic to validate the value against metadata_item's options.
        """
        metadata = self.metadata_item
        options = metadata.options

        if not options:
            return

        if metadata.data_type == MetadataDataTypes.SELECT:
            # Ensure the value is one of the available options
            if self.value not in options:
                raise ValidationError(f"Invalid value: {self.value}. Must be one of {options}.")

        elif metadata.data_type == MetadataDataTypes.MULTISELECT:
            # For multiselect, split the value and ensure all selected items are in options
            selected_values = [v.strip() for v in self.value.split(",")]
            invalid_values = [v for v in selected_values if v not in options]

            if invalid_values:
                raise ValidationError(f"Invalid values: {', '.join(invalid_values)}. Must be one of {options}.")

    def save(self, *args, **kwargs):
        """
        Override save to apply validation before saving.
        """
        self.clean()  # Call custom clean method to trigger validation
        super(DatasetMetadata, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.dataset.title} - {self.metadata_item.label}: {self.value}"
