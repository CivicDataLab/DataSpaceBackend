import uuid
from django.db import models

from api.types.SerializableJSONField import SerializableJSONField
from api.utils.enums import ChartTypes, AggregateType
from api.models import Resource, ResourceSchema

class ResourceChartDetails(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    chart_type = models.CharField(max_length=50, choices=ChartTypes.choices, default=ChartTypes.BAR_HORIZONTAL,
                                  blank=False, unique=False)
    options = SerializableJSONField(blank=True, default=dict)
    modified = models.DateTimeField(auto_now=True)
    filters = SerializableJSONField(blank=True, default=list)

    def __str__(self):
        return self.name
