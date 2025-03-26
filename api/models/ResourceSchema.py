from typing import TYPE_CHECKING

from django.db import models

from api.utils.enums import FieldTypes

if TYPE_CHECKING:
    from api.models.Resource import Resource


class ResourceSchema(models.Model):
    resource = models.ForeignKey(
        "api.Resource", on_delete=models.CASCADE, null=False, blank=False
    )
    field_name = models.CharField(max_length=255, null=False, blank=False)
    format = models.CharField(
        max_length=255, null=False, blank=False, choices=FieldTypes.choices
    )
    description = models.CharField(max_length=1000, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_schema"
