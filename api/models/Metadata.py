from django.db import models

from api.enums import MetadataStandards, MetadataDataTypes, MetadataTypes, MetadataModels


class Metadata(models.Model):
    label = models.CharField(max_length=75, unique=False)
    data_standard = models.CharField(max_length=50, choices=MetadataStandards.choices, blank=True, unique=False)
    urn = models.CharField(max_length=175, unique=True, blank=True)
    data_type = models.CharField(max_length=50, choices=MetadataDataTypes.choices, blank=False, unique=False)
    # TODO: detail options maybe with json field
    options = models.JSONField(blank=True, null=True)  # for select and multiselect
    # TODO: Add predefined set of validators and corresponding implementation
    validator = models.CharField(max_length=75, unique=False, blank=True)  # predefined set
    type = models.CharField(max_length=50, choices=MetadataTypes.choices, blank=False, unique=False)
    model = models.CharField(max_length=50, choices=MetadataModels.choices, blank=False, unique=False)
    enabled = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)
