from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction
from django.utils.text import slugify

if TYPE_CHECKING:
    from api.models.Dataset import Dataset
    from api.models.Organization import Organization
    from authorization.models import User

from api.utils.enums import CollaborativeStatus, OrganizationRelationshipType
from api.utils.file_paths import _use_case_directory_path
from api.utils.public_links import (
    PUBLIC_ID_LENGTH,
    build_url_slug,
    generate_public_id,
    save_with_public_id,
)
from api.utils.storage import public_storage

slug_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    message="Slug must be lowercase and contain only alphanumeric characters and hyphens.",
)


def _slug_with_suffix(base: str) -> str:
    """``base`` plus 4 random characters, kept within the 75-character limit."""
    return f"{base[:70].rstrip('-')}-{generate_public_id()[:4]}"


class Collaborative(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, blank=True, null=True)
    summary = models.TextField(max_length=200_000, blank=True, null=True)
    logo = models.ImageField(
        upload_to=_use_case_directory_path,
        storage=public_storage,
        max_length=300,
        blank=True,
        null=True,
    )
    cover_image = models.ImageField(
        upload_to=_use_case_directory_path,
        storage=public_storage,
        max_length=300,
        blank=True,
        null=True,
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    # Unique: the slug is also the collaborative's subdomain. Page links use public_id.
    slug = models.SlugField(
        max_length=75, null=True, blank=True, unique=True, validators=[slug_validator]
    )
    public_id = models.CharField(max_length=PUBLIC_ID_LENGTH, unique=True, editable=False)
    user = models.ForeignKey("authorization.User", on_delete=models.CASCADE)
    organization = models.ForeignKey(
        "api.Organization", on_delete=models.CASCADE, null=True, blank=True
    )
    status = models.CharField(
        max_length=50,
        default=CollaborativeStatus.DRAFT,
        choices=CollaborativeStatus.choices,
    )
    datasets = models.ManyToManyField("api.Dataset", blank=True)
    publications = models.ManyToManyField("api.Publication", blank=True)
    use_cases = models.ManyToManyField("api.UseCase", blank=True)
    tags = models.ManyToManyField("api.Tag", blank=True)
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="collaboratives")
    sdgs = models.ManyToManyField("api.SDG", blank=True, related_name="collaboratives")
    geographies = models.ManyToManyField("api.Geography", blank=True, related_name="collaboratives")
    contributors = models.ManyToManyField(
        "authorization.User", blank=True, related_name="contributed_collaboratives"
    )
    # Organizations can be added as supporters or partners through the intermediate model
    organizations = models.ManyToManyField(
        "api.Organization",
        through="api.CollaborativeOrganizationRelationship",
        related_name="related_collaboratives",
        blank=True,
    )
    started_on = models.DateField(blank=True, null=True)
    completed_on = models.DateField(blank=True, null=True)
    platform_url = models.URLField(blank=True, null=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        base = ""
        if self.title and not self.slug:
            base = slugify(cast(str, self.title))[:75].strip("-")
            if base:
                taken = Collaborative.objects.filter(slug=base).exclude(pk=self.pk).exists()
                self.slug = _slug_with_suffix(base) if taken else base

        def do_save() -> None:
            # public_id clashes are caught by the database and retried, not here.
            self.full_clean(exclude=["public_id"])
            super(Collaborative, self).save(*args, **kwargs)

        # Titles may repeat but slugs may not. A slug made from the title that
        # another save took in the meantime gets a new suffix; a slug the owner
        # typed is never changed (full_clean refuses it if taken).
        for attempt in range(3):
            try:
                with transaction.atomic():
                    save_with_public_id(self, do_save)
                return
            except IntegrityError as exc:
                if not base or "slug" not in str(exc) or attempt == 2:
                    raise
                self.slug = _slug_with_suffix(base)

    @property
    def url_slug(self) -> str:
        return build_url_slug(self.title, self.public_id)

    @property
    def is_individual_collaborative(self):
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
        db_table = "collaborative"
