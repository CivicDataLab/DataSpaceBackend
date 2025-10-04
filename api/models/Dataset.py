import uuid
from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import Sum
from django.utils.text import slugify

from api.utils.enums import DatasetAccessType, DatasetLicense, DatasetStatus

if TYPE_CHECKING:
    from api.models.DataSpace import DataSpace
    from api.models.Organization import Organization
    from api.models.Sector import Sector
    from authorization.models import User


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
    user = models.ForeignKey(
        "authorization.User",
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
    geographies = models.ManyToManyField(
        "api.Geography", blank=True, related_name="datasets"
    )
    access_type = models.CharField(
        max_length=50,
        default=DatasetAccessType.PUBLIC,
        choices=DatasetAccessType.choices,
    )
    license = models.CharField(
        max_length=50,
        default=DatasetLicense.CC_BY_4_0_ATTRIBUTION,
        choices=DatasetLicense.choices,
    )

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
    def geographies_indexing(self) -> list[str]:
        """Geographies for indexing.

        Used in Elasticsearch indexing.
        """
        return [geo.name for geo in self.geographies.all()]  # type: ignore

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
    def catalogs_indexing(self) -> list[str]:
        """Catalogs for indexing.

        Used in Elasticsearch indexing.
        """
        return [catalog.name for catalog in self.catalogs.all()]  # type: ignore

    @property
    def has_charts(self) -> bool:
        """Has charts or chart images.

        Used in Elasticsearch indexing.
        """
        has_charts = self.resources.filter(resourcechartdetails__isnull=False).exists()
        has_chart_images = self.chart_images.exists()
        return has_charts or has_chart_images

    @property
    def download_count(self) -> int:
        return (
            self.resources.aggregate(total_downloads=Sum("download_count"))[
                "total_downloads"
            ]
            or 0
        )

    @property
    def is_individual_dataset(self) -> bool:
        """Check if the dataset is an created by an individual."""
        return self.organization is None and self.user is not None

    @property
    def trending_score(self) -> float:
        """
        Calculate a trending score based on download count and recency.

        This score prioritizes datasets with recent download activity.
        Higher scores indicate more trending datasets.
        """
        from datetime import timedelta

        from django.db.models import ExpressionWrapper, F, fields
        from django.utils import timezone

        # Get recent downloads (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get resources with recent download activity
        recent_resources = self.resources.filter(modified__gte=thirty_days_ago)

        # Base score is the total download count
        base_score = self.download_count

        # If no recent activity, return a lower score
        if not recent_resources.exists():
            return float(base_score) * 0.1

        # Calculate recency factor (more recent = higher score)
        recent_downloads = (
            recent_resources.aggregate(total=Sum("download_count"))["total"] or 0
        )

        # Calculate trending score: base score + (recent downloads * recency factor)
        recency_factor = 2.0  # Weight for recent downloads
        trending_score = float(base_score) + (float(recent_downloads) * recency_factor)

        return trending_score

    def __str__(self) -> str:
        return self.title

    class Meta:
        verbose_name = "Dataset"
        verbose_name_plural = "Datasets"
        db_table = "dataset"
        ordering = ["-modified"]
