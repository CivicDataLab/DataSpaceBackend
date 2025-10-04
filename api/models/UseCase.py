from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils.text import slugify

if TYPE_CHECKING:
    from api.models.Dataset import Dataset
    from api.models.Organization import Organization
    from authorization.models import User

from api.utils.enums import (
    OrganizationRelationshipType,
    UseCaseRunningStatus,
    UseCaseStatus,
)
from api.utils.file_paths import _use_case_directory_path


class UseCase(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, unique=True, blank=True, null=True)
    summary = models.CharField(max_length=10000, blank=True, null=True)
    logo = models.ImageField(
        upload_to=_use_case_directory_path, max_length=300, blank=True, null=True
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    slug = models.SlugField(max_length=75, null=True, blank=True, unique=True)
    user = models.ForeignKey("authorization.User", on_delete=models.CASCADE)
    organization = models.ForeignKey(
        "api.Organization", on_delete=models.CASCADE, null=True, blank=True
    )
    status = models.CharField(
        max_length=50, default=UseCaseStatus.DRAFT, choices=UseCaseStatus.choices
    )
    datasets = models.ManyToManyField("api.Dataset", blank=True)
    tags = models.ManyToManyField("api.Tag", blank=True)
    running_status = models.CharField(
        max_length=50,
        default=UseCaseRunningStatus.INITIATED,
        choices=UseCaseRunningStatus.choices,
    )
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="usecases")
    sdgs = models.ManyToManyField("api.SDG", blank=True, related_name="usecases")
    geographies = models.ManyToManyField(
        "api.Geography", blank=True, related_name="usecases"
    )
    contributors = models.ManyToManyField(
        "authorization.User", blank=True, related_name="contributed_usecases"
    )
    # Organizations can be added as supporters or partners through the intermediate model
    organizations = models.ManyToManyField(
        "api.Organization",
        through="api.UseCaseOrganizationRelationship",
        related_name="related_usecases",
        blank=True,
    )
    started_on = models.DateField(blank=True, null=True)
    completed_on = models.DateField(blank=True, null=True)
    platform_url = models.URLField(blank=True, null=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.title and not self.slug:
            self.slug = slugify(cast(str, self.title))
        super().save(*args, **kwargs)

    @property
    def is_individual_usecase(self):
        return self.organization is None

    @property
    def sectors_indexing(self):
        return [sector.name for sector in self.sectors.all()]  # type: ignore

    @property
    def tags_indexing(self):
        return [tag.value for tag in self.tags.all()]  # type: ignore

    @property
    def sdgs_indexing(self):
        return [sdg.code for sdg in self.sdgs.all()]  # type: ignore

    @property
    def geographies_indexing(self):
        return [geo.name for geo in self.geographies.all()]  # type: ignore

    class Meta:
        db_table = "use_case"
