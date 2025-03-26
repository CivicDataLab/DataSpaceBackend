import uuid
from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils.text import slugify

from api.utils.enums import DatasetStatus

if TYPE_CHECKING:
    from api.models.DataSpace import DataSpace
    from api.models.Organization import Organization
    from api.models.Sector import Sector


class Tag(models.Model):
    value = models.CharField(max_length=50, unique=True, blank=False)

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        db_table = "tag"

    def __str__(self) -> str:
        return str(self.value)


class Dataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=True)
    organization = models.ForeignKey(
        "api.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datasets",
    )
    dataspace = models.ForeignKey(
        "api.DataSpace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datasets",
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField("api.Tag", blank=True)
    status = models.CharField(
        max_length=50, default=DatasetStatus.DRAFT, choices=DatasetStatus.choices
    )
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="datasets")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def tags_indexing(self) -> list[str]:
        """Tags for indexing.

        Used in Elasticsearch indexing.
        """
        return [tag.value for tag in self.tags.all()]  # type: ignore

    @property
    def sectors_indexing(self) -> list[str]:
        """Sectors for indexing.

        Used in Elasticsearch indexing.
        """
        return [sector.name for sector in self.sectors.all()]  # type: ignore

    @property
    def formats_indexing(self) -> list[str]:
        """Formats for indexing.

        Used in Elasticsearch indexing.
        """
        return list(
            set(
                [
                    resource.resourcefiledetails.format  # type: ignore
                    for resource in self.resources.all()
                ]
            ).difference({""})
        )

    @property
    def has_charts(self) -> bool:
        """Has charts.

        Used in Elasticsearch indexing.
        """
        return bool(self.resources.filter(resourcechartdetails__isnull=False).exists())

    def __str__(self) -> str:
        return self.title

    class Meta:
        verbose_name = "Dataset"
        verbose_name_plural = "Datasets"
        db_table = "dataset"
        ordering = ["-modified"]
