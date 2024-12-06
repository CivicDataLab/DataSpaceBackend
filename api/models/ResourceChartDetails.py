import uuid

from django.db import models

from api.utils.enums import ChartTypes, AggregateType
from api.models import Resource, ResourceSchema


class ResourceChartDetails(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    chart_type = models.CharField(max_length=50, choices=ChartTypes.choices, default=ChartTypes.BAR_HORIZONTAL,
                                  blank=False, unique=False)
    x_axis_label = models.CharField(max_length=50, default="")
    y_axis_label = models.CharField(max_length=50, default="")
    x_axis_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=True, blank=True, related_name="x_column")
    y_axis_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=True, blank=True, related_name="y_column")
    show_legend = models.BooleanField(default=False)
    aggregate_type = models.CharField(max_length=50, choices=AggregateType.choices, default=AggregateType.NONE,
                                      blank=False, unique=False)
    region_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=True, blank=True, related_name="region")
    value_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=True, blank=True, related_name="value")
    modified = models.DateTimeField(auto_now=True)
    filters = models.JSONField(blank=True, default=list)

    def __str__(self):
        return self.name
