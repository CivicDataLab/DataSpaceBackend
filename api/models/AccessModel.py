import uuid
from typing import TYPE_CHECKING

from django.db import models

from api.utils.enums import AccessTypes

if TYPE_CHECKING:
    from api.models.Dataset import Dataset
    from api.models.Organization import Organization
    from api.models.Resource import Resource


class AccessModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, unique=False, blank=True, null=True)
    description = models.CharField(max_length=1000, unique=False, blank=True, null=True)
    dataset = models.ForeignKey(
        "api.Dataset", on_delete=models.CASCADE, null=False, blank=False
    )
    type = models.CharField(
        max_length=100,
        unique=False,
        blank=False,
        choices=AccessTypes.choices,
        default=AccessTypes.PUBLIC,
    )
    organization = models.ForeignKey(
        "api.Organization", on_delete=models.CASCADE, null=True, blank=True
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "access_model"


class AccessModelResource(models.Model):
    access_model = models.ForeignKey(
        "api.AccessModel", on_delete=models.CASCADE, null=False, blank=False
    )
    resource = models.ForeignKey(
        "api.Resource", on_delete=models.CASCADE, null=False, blank=False
    )
    fields = models.ManyToManyField("api.ResourceSchema")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "access_model_resource"
