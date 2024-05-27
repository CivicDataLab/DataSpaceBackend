import uuid

from django.db import models

from api.enums import DatasetStatus
from api.models import Organization, Category


class Tag(models.Model):
    value = models.CharField(max_length=50, unique=True, blank=False)

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

    def __str__(self):
        return self.value


class Dataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, blank=True)
    status = models.CharField(max_length=50, default=DatasetStatus.DRAFT, choices=DatasetStatus.choices)
    categories = models.ManyToManyField(Category, blank=True)

    @property
    def tags_indexing(self):
        """Tags for indexing.

        Used in Elasticsearch indexing.
        """
        return [tag.value for tag in self.tags.all()]

    @property
    def categories_indexing(self):
        """Tags for indexing.

        Used in Elasticsearch indexing.
        """
        return [category.value for category in self.categories.all()]
