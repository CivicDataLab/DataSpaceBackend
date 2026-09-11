import uuid
from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from api.utils.enums import DatasetLicense, PublicationBlockType, PublicationStatus
from api.utils.file_paths import _publication_block_directory_path

if TYPE_CHECKING:
    from api.models.Organization import Organization
    from api.models.ResourceType import ResourceType
    from authorization.models import User


class Publication(models.Model):
    """A top-level Resource — a container for human-authored content.

    Peer to Dataset and AI Model: a UUID/slug entity owned by an organization or
    an individual user, with typed metadata columns, a publish/unpublish status,
    an ordered list of content blocks, and its own search + linking surface.
    (Internal name ``Publication`` to avoid colliding with the file-inside-a-dataset
    ``Resource``; the UI always labels it "Resource".)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, unique=False, blank=True)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=True)

    organization = models.ForeignKey(
        "api.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publications",
    )
    user = models.ForeignKey(
        "authorization.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publications",
    )

    # Typed metadata columns — a fixed, known schema (no dynamic/EAV fields).
    authors = models.JSONField(default=list, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    license = models.CharField(
        max_length=50,
        default=DatasetLicense.CC_BY_4_0_ATTRIBUTION,
        choices=DatasetLicense.choices,
    )
    external_source_link = models.URLField(blank=True, null=True)

    # Structural / faceted columns.
    status = models.CharField(
        max_length=50,
        default=PublicationStatus.DRAFT,
        choices=PublicationStatus.choices,
    )
    resource_type = models.ForeignKey(
        "api.ResourceType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="publications",
    )
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="publications")
    geographies = models.ManyToManyField("api.Geography", blank=True, related_name="publications")
    download_count = models.IntegerField(default=0)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Publication.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_individual_publication(self) -> bool:
        """True when this Resource is owned by an individual, not an organization."""
        return self.organization is None and self.user is not None

    @property
    def sectors_indexing(self) -> list[str]:
        """Sector names for Elasticsearch indexing."""
        return [sector.name for sector in self.sectors.all()]  # type: ignore

    @property
    def geographies_indexing(self) -> list[str]:
        """Geography names for Elasticsearch indexing."""
        return [geo.name for geo in self.geographies.all()]  # type: ignore

    @property
    def resource_type_indexing(self) -> str:
        """Resource-type name for Elasticsearch indexing (empty when unset)."""
        return self.resource_type.name if self.resource_type else ""

    def __str__(self) -> str:
        return self.title

    class Meta:
        verbose_name = "Publication"
        verbose_name_plural = "Publications"
        db_table = "publication"
        ordering = ["-modified"]
        indexes = [
            models.Index(fields=["organization", "-modified"]),
            models.Index(fields=["user", "-modified"]),
            models.Index(fields=["status"]),
        ]


class PublicationBlock(models.Model):
    """One content block in a Resource — a file XOR a YouTube embed, at a position.

    Blocks are ordered by ``position`` within their publication. Each block is
    exactly one of two shapes, enforced by the ``file_xor_youtube`` check
    constraint: a FILE block carries an uploaded file (with its name/format/size),
    a YOUTUBE block carries a video url and its extracted id. Neither-both nor
    neither-set is a valid row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        "api.Publication",
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    position = models.PositiveIntegerField(default=0)
    block_type = models.CharField(
        max_length=20,
        choices=PublicationBlockType.choices,
    )

    # FILE block fields.
    file = models.FileField(
        upload_to=_publication_block_directory_path,
        max_length=300,
        blank=True,
    )
    file_name = models.CharField(max_length=300, blank=True)
    file_format = models.CharField(max_length=50, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)

    # YOUTUBE block fields.
    youtube_url = models.URLField(blank=True, null=True)
    youtube_video_id = models.CharField(max_length=20, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.block_type} block #{self.position} of {self.publication_id}"

    class Meta:
        db_table = "publication_block"
        ordering = ["position"]
        indexes = [
            models.Index(fields=["publication", "position"]),
        ]
        constraints = [
            # Runtime is Django 5.0 (``check=``); the pinned django-stubs is
            # newer and only knows the 5.1 ``condition=`` spelling, hence the
            # ignore. Switch to ``condition=`` when the runtime moves to 5.1+.
            models.CheckConstraint(  # type: ignore[call-arg]
                name="publicationblock_file_xor_youtube",
                check=(
                    Q(
                        block_type=PublicationBlockType.FILE,
                        youtube_url__isnull=True,
                    )
                    & ~Q(file="")
                )
                | Q(
                    block_type=PublicationBlockType.YOUTUBE,
                    file="",
                    youtube_url__isnull=False,
                ),
            )
        ]
