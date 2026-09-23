"""Turn a third-party platform dataset into a DataSpace Dataset (link-only).

Creates the Dataset (DRAFT), a single EXTERNAL Resource that links to the
dataset's page on the platform, a DatasetSource provenance row, tags, taxonomy
and metadata prefill, and the creator's owner permission — all inside one
transaction. Files are never listed or copied: people reach them through the
original dataset link.
"""

from __future__ import annotations

from typing import Iterable, Optional

import structlog
from django.db import transaction
from django.utils.text import slugify

from api.models import (
    Dataset,
    DatasetMetadata,
    DatasetSource,
    DataSpace,
    Geography,
    Metadata,
    Organization,
    Resource,
    ResourceSchema,
    Sector,
    Tag,
)
from api.services.platform_importers import (
    PlatformDatasetInfo,
    PlatformImportError,
    get_importer,
)
from api.utils.enums import (
    DatasetAccessType,
    DatasetStatus,
    DatasetType,
    DataType,
    MetadataModels,
)
from authorization.models import DatasetPermission, Role, User

logger = structlog.get_logger("dataspace.platform_import")


class DuplicateImportError(PlatformImportError):
    """The same platform dataset was already imported into this publisher scope."""

    def __init__(self, existing: Dataset) -> None:
        super().__init__(
            f"This dataset was already imported as '{existing.title}' ({existing.slug})"
        )
        self.existing = existing


def preview_platform_dataset(platform: str, identifier: str) -> PlatformDatasetInfo:
    """Fetch normalised metadata without creating anything."""
    importer = get_importer(platform)
    return importer.fetch_dataset_info(identifier)


def find_existing_import(
    platform: str,
    identifier: str,
    organization: Optional[Organization],
    user: Optional[User],
) -> Optional[Dataset]:
    """Return a dataset already imported from this source in the same scope.

    Scope is the organization when importing on its behalf, otherwise the
    individual user — mirroring how datasets are owned elsewhere.
    """
    qs = DatasetSource.objects.select_related("dataset").filter(
        platform=platform, source_identifier=identifier
    )
    if organization is not None:
        qs = qs.filter(dataset__organization=organization)
    else:
        qs = qs.filter(dataset__organization__isnull=True, dataset__user=user)
    source = qs.first()
    return source.dataset if source else None


def _unique_dataset_slug(title: str) -> str:
    """Pick a free slug up front. Dataset.save() retries on a slug collision,
    but only a handful of times; platform titles ("Iris", "Wine Reviews")
    repeat across organisations far more often than timestamped native ones,
    so choose a free slug before saving rather than rely on the retry."""
    base = slugify(title)[:240] or "imported-dataset"
    slug, counter = base, 2
    while Dataset.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


PLATFORM_LABELS = {"HUGGINGFACE": "Hugging Face", "KAGGLE": "Kaggle", "GITHUB": "GitHub"}


# Platform tags/topics are matched (case-insensitively) against our own
# taxonomies so the publisher lands on the metadata step with sectors and
# geographies already ticked where the names line up. Publishing requires
# sectors, so this is the most valuable prefill we can do without a human.
def _prefill_taxonomies(dataset: Dataset, tags: Iterable[str]) -> None:
    names = {t.strip().lower() for t in tags if t and t.strip()}
    if not names:
        return
    sectors = [s for s in Sector.objects.all() if s.name.strip().lower() in names]
    if sectors:
        dataset.sectors.add(*sectors)
    geographies = [g for g in Geography.objects.all() if g.name.strip().lower() in names]
    if geographies:
        dataset.geographies.add(*geographies)


# Optional EAV prefill: if the deployment defines dataset metadata fields whose
# label matches one of these (case-insensitive), fill it from the platform.
# Deployments without such fields are simply skipped.
METADATA_LABEL_SOURCES = {
    "source": "source_url",
    "source url": "source_url",
    "source platform": "platform_label",
    "original source": "source_url",
    "author": "author",
    "creator": "author",
    "publisher": "author",
    "license": "license",
    "original license": "license",
    "last updated": "last_updated",
    "source last updated": "last_updated",
}


def _prefill_metadata(dataset: Dataset, info: PlatformDatasetInfo) -> None:
    values = {
        "source_url": info.source_url,
        "platform_label": PLATFORM_LABELS.get(str(info.platform), str(info.platform).title()),
        "author": info.author,
        "license": info.license,
        "last_updated": info.last_updated.date().isoformat() if info.last_updated else "",
    }
    fields = Metadata.objects.filter(enabled=True, model=MetadataModels.DATASET)
    for field in fields:
        source_key = METADATA_LABEL_SOURCES.get((field.label or "").strip().lower())
        value = values.get(source_key or "", "")
        if not value:
            continue
        try:
            DatasetMetadata(dataset=dataset, metadata_item=field, value=str(value)[:1000]).save()
        except Exception as exc:  # validators on the field may reject the value; that's fine
            logger.info("platform_import_metadata_skipped", label=field.label, error=str(exc))


@transaction.atomic
def import_platform_dataset(
    *,
    platform: str,
    identifier: str,
    user: User,
    organization: Optional[Organization] = None,
    dataspace: Optional[DataSpace] = None,
    info: Optional[PlatformDatasetInfo] = None,
    title: Optional[str] = None,
) -> Dataset:
    """Create a DRAFT dataset from a platform source. Raises PlatformImportError."""
    importer = get_importer(platform)
    canonical_id = importer.parse_identifier(identifier)

    existing = find_existing_import(platform, canonical_id, organization, user)
    if existing is not None:
        raise DuplicateImportError(existing)

    if info is None:
        info = importer.fetch_dataset_info(canonical_id)

    # Publisher may choose the name shown on DataSpace; platform title otherwise.
    display_title = (title or "").strip()[:300] or info.title
    dataset = Dataset.objects.create(
        title=display_title,
        slug=_unique_dataset_slug(display_title),
        description=info.description,
        user=user,
        organization=organization,
        dataspace=dataspace,
        status=DatasetStatus.DRAFT,
        access_type=DatasetAccessType.PUBLIC,
        license=info.mapped_license,
        dataset_type=DatasetType.DATA,
    )

    if info.tags:
        tags = [
            Tag.objects.get_or_create(defaults={"value": value}, value__iexact=value)[0]
            for value in info.tags
        ]
        dataset.tags.set(tags)
        _prefill_taxonomies(dataset, info.tags)
    _prefill_metadata(dataset, info)

    # One resource standing for the whole dataset on the platform. Its URL is
    # the dataset page, so "download" redirects there and people browse/fetch
    # files with the platform's own tooling.
    platform_label = PLATFORM_LABELS.get(str(info.platform), str(info.platform).title())
    link_resource = Resource.objects.create(
        dataset=dataset,
        type=DataType.EXTERNAL,
        name=f"Dataset on {platform_label}"[:200],
        url=info.source_url[:500],
        description=f"Files are hosted on {platform_label}. Open the link to browse and download them.",
    )

    DatasetSource.objects.create(
        dataset=dataset,
        platform=info.platform,
        source_identifier=info.identifier,
        source_url=info.source_url[:500],
        source_homepage=(info.homepage or "")[:500],
        revision=(info.revision or "")[:64],
        source_author=info.author[:300],
        source_license=info.license[:300],
        source_readme=info.readme or "",
        citation=info.citation or "",
        languages=list(info.languages or []),
        source_created_at=info.created_at,
        source_last_updated=info.last_updated,
        is_archived=bool(info.is_archived),
        imported_by=user,
    )

    # Column definitions the platform declared (Hugging Face dataset_info).
    # They live on the link resource so "View All Columns" and the Croissant
    # recordSet work without any data being fetched.
    ResourceSchema.objects.bulk_create(
        [
            ResourceSchema(resource=link_resource, field_name=col.name, format=col.field_type)
            for col in info.columns
        ]
    )

    try:
        owner_role = Role.objects.get(name="owner")
    except Role.DoesNotExist as exc:
        # Same seed the rest of the app relies on (add_dataset does a bare .get()).
        raise PlatformImportError(
            "Roles are not initialised on this server (run `manage.py init_roles`)"
        ) from exc
    DatasetPermission.objects.create(user=user, dataset=dataset, role=owner_role)

    logger.info(
        "platform_dataset_imported",
        platform=info.platform,
        identifier=info.identifier,
        dataset_id=str(dataset.id),
        user_id=str(user.id),
    )
    return dataset
