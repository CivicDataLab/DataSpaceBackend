"""
publication_service
────────────────────
Domain helpers for the Publication ("Resource") CRUD flow — the messy 90% the
``publication_schema`` flow file delegates to. Each function does one thing:
validate the metadata at the input boundary, create/update the row, flip its
publish status, or return the correctly-scoped queryset for a listing.

These never talk to GraphQL types or permissions — they take plain values and
model instances, so they're unit-testable on their own.
"""

from typing import Any, List, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db.models import QuerySet

from api.models import Geography, Publication, ResourceType, Sector
from api.utils.enums import DatasetLicense, PublicationStatus

# Default page size + hard ceiling for a publications listing, enforced even
# when the caller sends no pagination input.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def validate_publication_metadata(
    *,
    title: Optional[str],
    description: Optional[str],
    authors: Optional[List[str]],
    publication_date: Any,
    license_value: Optional[str],
    resource_type_id: Any,
    sector_ids: Optional[List[Any]],
    geography_ids: Optional[List[Any]],
    external_source_link: Optional[str],
) -> ResourceType:
    """Validate a resource's metadata at the create boundary.

    Enforces the required fields (title, description, authors, publication_date,
    license, an active resource type, at least one sector and one geography),
    the controlled license vocabulary, and the optional external link's URL
    shape. Raises a field-keyed ``ValidationError`` on any problem and returns
    the resolved active ``ResourceType`` on success.
    """
    errors: dict[str, List[str]] = {}

    if not title or not title.strip():
        errors["title"] = ["Title is required."]
    if not description or not description.strip():
        errors["description"] = ["Description is required."]
    if not authors or not [a for a in authors if a and a.strip()]:
        errors["authors"] = ["At least one author is required."]
    if publication_date is None:
        errors["publication_date"] = ["Publication date is required."]
    if not sector_ids:
        errors["sectors"] = ["At least one sector is required."]
    if not geography_ids:
        errors["geographies"] = ["At least one geography is required."]

    if not license_value:
        errors["license"] = ["License is required."]
    elif license_value not in DatasetLicense.values:
        errors["license"] = ["Not a valid license."]

    if external_source_link:
        try:
            URLValidator()(external_source_link)
        except DjangoValidationError:
            errors["external_source_link"] = ["Enter a valid URL."]

    resource_type = _resolve_active_resource_type(resource_type_id, errors)

    if errors:
        raise DjangoValidationError(errors)

    return resource_type  # type: ignore[return-value]


def _resolve_active_resource_type(
    resource_type_id: Any, errors: dict[str, List[str]]
) -> Optional[ResourceType]:
    """Load the resource type and require it to exist and be active."""
    if not resource_type_id:
        errors["resource_type"] = ["Resource type is required."]
        return None
    try:
        resource_type = ResourceType.objects.get(id=resource_type_id)
    except ResourceType.DoesNotExist:
        errors["resource_type"] = ["Resource type does not exist."]
        return None
    if not resource_type.is_active:
        errors["resource_type"] = ["Resource type is not active."]
        return None
    return resource_type


def create_publication(
    *,
    user: Any,
    organization: Any,
    title: str,
    description: Optional[str],
    authors: List[str],
    publication_date: Any,
    license_value: str,
    resource_type: ResourceType,
    sector_ids: List[Any],
    geography_ids: List[Any],
    external_source_link: Optional[str],
) -> Publication:
    """Create a DRAFT publication from validated metadata and wire its M2M tags.

    Ownership follows the caller's context: an organization present in the
    request makes it org-owned, otherwise it's the individual user's.
    """
    publication = Publication.objects.create(
        title=title,
        description=description,
        authors=authors,
        publication_date=publication_date,
        license=license_value,
        resource_type=resource_type,
        external_source_link=external_source_link or None,
        organization=organization,
        user=user,
        status=PublicationStatus.DRAFT,
    )
    _set_publication_tags(publication, sector_ids, geography_ids)
    return publication


def apply_publication_update(
    publication: Publication,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    authors: Optional[List[str]] = None,
    publication_date: Any = None,
    license_value: Optional[str] = None,
    resource_type_id: Any = None,
    sector_ids: Optional[List[Any]] = None,
    geography_ids: Optional[List[Any]] = None,
    external_source_link: Optional[str] = None,
) -> Publication:
    """Apply a partial metadata update, validating each field that's provided.

    Only fields passed in are touched, so a subpage save never blanks columns it
    didn't show. A provided license must be in the controlled list; a provided
    resource type must be active; a provided link must be a valid URL.
    """
    errors: dict[str, List[str]] = {}

    if title is not None:
        publication.title = title
    if description is not None:
        publication.description = description
    if authors is not None:
        publication.authors = authors
    if publication_date is not None:
        publication.publication_date = publication_date
    if external_source_link is not None:
        if external_source_link:
            try:
                URLValidator()(external_source_link)
                publication.external_source_link = external_source_link
            except DjangoValidationError:
                errors["external_source_link"] = ["Enter a valid URL."]
        else:
            publication.external_source_link = None

    if license_value is not None:
        if license_value in DatasetLicense.values:
            publication.license = license_value
        else:
            errors["license"] = ["Not a valid license."]

    if resource_type_id is not None:
        resource_type = _resolve_active_resource_type(resource_type_id, errors)
        if resource_type is not None:
            publication.resource_type = resource_type

    if errors:
        raise DjangoValidationError(errors)

    publication.save()
    if sector_ids is not None or geography_ids is not None:
        _set_publication_tags(publication, sector_ids, geography_ids)
    return publication


def set_publication_status(publication: Publication, status: PublicationStatus) -> Publication:
    """Flip a publication's publish status and save it."""
    publication.status = status
    publication.save()
    return publication


def get_scoped_publications(
    *, user: Any, organization: Any, include_public: bool
) -> "QuerySet[Publication, Publication]":
    """Return the publications a caller may list, correctly scoped.

    Organization context → that org's publications; an authenticated individual
    → their own; anonymous → published only. ``include_public`` unions in the
    published set so a signed-in user also sees the public listing. Ordered
    newest-first and de-duplicated after the union.
    """
    if organization:
        queryset = Publication.objects.filter(organization=organization)
    elif getattr(user, "is_superuser", False):
        queryset = Publication.objects.all()
    elif getattr(user, "is_authenticated", False):
        queryset = Publication.objects.filter(user=user, organization__isnull=True)
    else:
        queryset = Publication.objects.filter(status=PublicationStatus.PUBLISHED)

    if include_public:
        queryset = queryset | Publication.objects.filter(status=PublicationStatus.PUBLISHED)

    return queryset.order_by("-modified").distinct()


def is_publication_published(publication: Publication) -> bool:
    """True only when the publication is PUBLISHED."""
    return publication.status == PublicationStatus.PUBLISHED.value


def resolve_pagination(offset: Optional[int], limit: Optional[int]) -> tuple[int, int]:
    """Turn a caller's optional page window into a bounded (offset, limit).

    A missing limit falls back to the default page size; any limit is capped at
    the hard maximum, so a listing is never unbounded even with no input.
    """
    safe_offset = max(offset or 0, 0)
    if not limit or limit <= 0:
        safe_limit = DEFAULT_PAGE_SIZE
    else:
        safe_limit = min(limit, MAX_PAGE_SIZE)
    return safe_offset, safe_limit


def _set_publication_tags(
    publication: Publication,
    sector_ids: Optional[List[Any]],
    geography_ids: Optional[List[Any]],
) -> None:
    """Replace a publication's sector and geography tags from id lists."""
    if sector_ids is not None:
        publication.sectors.set(Sector.objects.filter(id__in=sector_ids))
    if geography_ids is not None:
        publication.geographies.set(Geography.objects.filter(id__in=geography_ids))
