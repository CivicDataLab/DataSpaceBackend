from django.db import models

from api.utils.enums import GeoTypes


class Geography(models.Model):
    name = models.CharField(max_length=75, unique=True)
    code = models.CharField(max_length=100, null=True, blank=True, unique=False, default='')
    type = models.CharField(max_length=20, choices=GeoTypes.choices)
    parent_id = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, default='')
