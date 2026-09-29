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

import datetime
from typing import Any, List, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import QuerySet

from api.models import Geography, Publication, ResourceType, Sector
from api.utils.enums import DatasetLicense, PublicationStatus

# Default page size + hard ceiling for a publications listing, enforced even
# when the caller sends no pagination input.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def validate_draft_inputs(
    *,
    license_value: Optional[str] = None,
    resource_type_id: Any = None,
    external_source_link: Optional[str] = None,
) -> Optional[ResourceType]:
    """Check the shape of whatever a draft save actually sent.

    A draft may be a title, or empty. License, resource type, and the external
    link are checked only when present: an unknown license, an inactive
    resource type, or a malformed link is rejected, and a missing one is not.
    Returns the active resource type when one was sent.
    """
    errors: dict[str, List[str]] = {}
    resource_type = None

    if license_value and license_value not in DatasetLicense.values:
        errors["license"] = ["Not a valid license."]
    if resource_type_id:
        resource_type = _resolve_active_resource_type(resource_type_id, errors)
    if external_source_link:
        try:
            URLValidator()(external_source_link)
        except DjangoValidationError:
            errors["external_source_link"] = ["Enter a valid URL."]

    if errors:
        raise DjangoValidationError(errors)
    return resource_type


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
    """Validate a resource's metadata at the publish boundary.

    Enforces the required fields (title, description, authors, publication_date,
    license, an active resource type, at least one sector and one geography),
    the controlled license vocabulary, and the optional external link's URL
    shape. Raises a field-keyed ``ValidationError`` on any problem and returns
    the resolved active ``ResourceType`` on success. Draft create/update does
    not call this — a draft may be saved with only a title, or with nothing.
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
    title: str = "",
    description: Optional[str] = None,
    authors: Optional[List[str]] = None,
    publication_date: Any = None,
    license_value: Optional[str] = None,
    resource_type: Optional[ResourceType] = None,
    sector_ids: Optional[List[Any]] = None,
    geography_ids: Optional[List[Any]] = None,
    external_source_link: Optional[str] = None,
) -> Publication:
    """Create a draft and attach any sector or geography ids that were sent.

    A blank title is replaced with a generated one.     An organization on the
    request owns the row; otherwise the user does.
    """
    errors: dict[str, List[str]] = {}
    _reject_missing_tags(sector_ids or [], geography_ids or [], errors)
    if errors:
        raise DjangoValidationError(errors)

    with transaction.atomic():
        publication = Publication.objects.create(
            title=(title or "").strip() or _default_title(),
            description=(description or "").strip() or None,
            authors=_clean_authors(authors),
            publication_date=publication_date,
            license=license_value or DatasetLicense.CC_BY_4_0_ATTRIBUTION,
            resource_type=resource_type,
            external_source_link=external_source_link or None,
            organization=organization,
            user=user,
            status=PublicationStatus.DRAFT,
        )
        _set_publication_tags(publication, sector_ids or [], geography_ids or [])
    return publication


# Distinguishes "the caller omitted this field" from an explicit null/empty.
_UNSET: Any = object()


def apply_publication_update(
    publication: Publication,
    *,
    title: Any = _UNSET,
    description: Any = _UNSET,
    authors: Any = _UNSET,
    publication_date: Any = _UNSET,
    license_value: Any = _UNSET,
    resource_type_id: Any = _UNSET,
    sector_ids: Any = _UNSET,
    geography_ids: Any = _UNSET,
    external_source_link: Any = _UNSET,
) -> Publication:
    """Apply a partial metadata update. Omitted fields are left untouched.

    A draft may be saved incomplete — an empty title, description, or author
    list is stored as-is. A provided license must be in the controlled list, a
    provided resource type must be active, and a provided link must be a valid
    URL. A row that is already published cannot be saved back into an
    incomplete state; publish is what requires every field.
    """
    errors: dict[str, List[str]] = {}
    new_title = publication.title if title is _UNSET else (title or "").strip()
    new_description = (
        publication.description
        if description is _UNSET
        else ((description or "").strip() or None)
    )
    new_authors = publication.authors if authors is _UNSET else _clean_authors(authors)
    new_date = publication.publication_date if publication_date is _UNSET else publication_date
    new_link = publication.external_source_link
    if external_source_link is not _UNSET:
        if external_source_link:
            try:
                URLValidator()(external_source_link)
                new_link = external_source_link
            except DjangoValidationError:
                errors["external_source_link"] = ["Enter a valid URL."]
        else:
            new_link = None

    new_license = publication.license
    if license_value is not _UNSET and license_value:
        if license_value in DatasetLicense.values:
            new_license = license_value
        else:
            errors["license"] = ["Not a valid license."]

    new_resource_type = publication.resource_type
    if resource_type_id is not _UNSET:
        if resource_type_id:
            resolved = _resolve_active_resource_type(resource_type_id, errors)
            if resolved is not None:
                new_resource_type = resolved
        else:
            new_resource_type = None

    _reject_missing_tags(sector_ids, geography_ids, errors)
    if errors:
        raise DjangoValidationError(errors)

    kept_sectors = _tag_ids(sector_ids, publication.sectors)
    kept_geographies = _tag_ids(geography_ids, publication.geographies)
    if publication.status == PublicationStatus.PUBLISHED:
        validate_publication_metadata(
            title=new_title,
            description=new_description,
            authors=new_authors,
            publication_date=new_date,
            license_value=new_license,
            resource_type_id=getattr(new_resource_type, "id", None),
            sector_ids=kept_sectors,
            geography_ids=kept_geographies,
            external_source_link=new_link,
        )

    with transaction.atomic():
        publication.title = new_title
        publication.description = new_description
        publication.authors = new_authors
        publication.publication_date = new_date
        publication.external_source_link = new_link
        publication.license = new_license
        publication.resource_type = new_resource_type
        publication.save()
        if sector_ids is not _UNSET or geography_ids is not _UNSET:
            _set_publication_tags(
                publication,
                None if sector_ids is _UNSET or sector_ids is None else sector_ids,
                None if geography_ids is _UNSET or geography_ids is None else geography_ids,
            )
    return publication


def assert_ready_to_publish(publication: Publication) -> None:
    """Reject a publish when the draft is still missing a required field."""
    validate_publication_metadata(
        title=publication.title,
        description=publication.description,
        authors=list(publication.authors or []),
        publication_date=publication.publication_date,
        license_value=publication.license,
        resource_type_id=publication.resource_type_id,
        sector_ids=list(publication.sectors.values_list("id", flat=True)),
        geography_ids=list(publication.geographies.values_list("id", flat=True)),
        external_source_link=publication.external_source_link,
    )


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

    # Prefetch the relations the listing/card resolvers touch so a page of N
    # resources stays a bounded number of queries, not one-per-row.
    return (
        queryset.select_related("resource_type", "organization", "user")
        .prefetch_related("sectors", "geographies", "blocks")
        .order_by("-modified")
        .distinct()
    )


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


def _default_title() -> str:
    """Title for a publication created without one."""
    return f"New publication {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}"


def _clean_authors(authors: Optional[List[str]]) -> List[str]:
    """Author names with surrounding space and blanks removed."""
    return [author.strip() for author in (authors or []) if author and author.strip()]


def _tag_ids(incoming: Any, current: Any) -> List[Any]:
    """Ids used for the publish check. Null keeps the tags already stored."""
    if incoming is _UNSET or incoming is None:
        return list(current.values_list("id", flat=True))
    return list(incoming)


def _reject_missing_tags(sector_ids: Any, geography_ids: Any, errors: dict[str, List[str]]) -> None:
    """Record an error when a sent sector or geography id is not in the database."""
    if sector_ids is not _UNSET and sector_ids is not None:
        _require_existing_ids(
            Sector, sector_ids, "sectors", "One or more sectors do not exist.", errors
        )
    if geography_ids is not _UNSET and geography_ids is not None:
        _require_existing_ids(
            Geography,
            geography_ids,
            "geographies",
            "One or more geographies do not exist.",
            errors,
        )


def _require_existing_ids(
    model: Any, ids: List[Any], field: str, message: str, errors: dict[str, List[str]]
) -> None:
    requested = list(ids or [])
    if not requested:
        return
    found = {str(pk) for pk in model.objects.filter(id__in=requested).values_list("id", flat=True)}
    if any(str(item) not in found for item in requested):
        errors[field] = [message]


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
