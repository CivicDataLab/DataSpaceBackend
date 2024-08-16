import uuid

from django.db import models

from api.enums import DataType, ChartTypes, AggregateType
from api.models import Dataset, ResourceSchema


class Resource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name='resources')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=50, choices=DataType.choices, default=DataType.FILE, blank=False, unique=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    preview_enabled = models.BooleanField(default=False)
    preview_details = models.OneToOneField('ResourcePreviewDetails', on_delete=models.CASCADE, null=True, blank=True)


class ResourceFileDetails(models.Model):
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, null=False, blank=False)
    file = models.FileField(upload_to='resources/')
    size = models.FloatField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    format = models.CharField(max_length=50)


class ResourcePreviewDetails(models.Model):
    is_all_entries = models.BooleanField(default=True)
    start_entry = models.IntegerField(default=0)
    end_entry = models.IntegerField(default=10)


class ResourceChartDetails(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    chart_type = models.CharField(max_length=50, choices=ChartTypes.choices, default=ChartTypes.BAR_HORIZONTAL,
                                  blank=False, unique=False)
    x_axis_label = models.CharField(max_length=50)
    y_axis_label = models.CharField(max_length=50)
    x_axis_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=False, blank=False)
    y_axis_column = models.ForeignKey(ResourceSchema, on_delete=models.CASCADE, null=False, blank=False)
    show_legend = models.BooleanField(default=False)
    aggregate_type = models.CharField(max_length=50, choices=AggregateType.choices, default=AggregateType.NONE,
                                      blank=False, unique=False)
