from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models import Dataset, Organization, Sector, UseCase
from api.utils.enums import DatasetStatus, UseCaseStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

# Create separate indices for each publisher document type
ORG_INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[f"{__name__}.OrganizationPublisherDocument"])
ORG_INDEX.settings(number_of_shards=1, number_of_replicas=0)

USER_INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[f"{__name__}.UserPublisherDocument"])
USER_INDEX.settings(number_of_shards=1, number_of_replicas=0)


class PublisherDocument(Document):
    """Elasticsearch document for Publisher (Organization and User) models."""

    # Common fields for both organizations and users
    name = fields.TextField(
        analyzer=ngram_analyser,
        fields={
            "raw": KeywordField(multi=False),
        },
    )

    description = fields.TextField(
        analyzer=html_strip,
        fields={
            "raw": fields.TextField(analyzer="keyword"),
        },
    )

    publisher_type = fields.KeywordField()  # 'organization' or 'user'

    # Organization specific fields
    logo = fields.TextField(analyzer=ngram_analyser)
    homepage = fields.TextField(analyzer=ngram_analyser)
    contact_email = fields.KeywordField()
    organization_types = fields.KeywordField()
    github_profile = fields.TextField(analyzer=ngram_analyser)
    linkedin_profile = fields.TextField(analyzer=ngram_analyser)
    twitter_profile = fields.TextField(analyzer=ngram_analyser)
    location = fields.TextField(analyzer=ngram_analyser)

    # User specific fields
    bio = fields.TextField(
        analyzer=html_strip,
        fields={
            "raw": fields.TextField(analyzer="keyword"),
        },
    )
    profile_picture = fields.TextField(analyzer=ngram_analyser)
    username = fields.KeywordField()
    email = fields.KeywordField()
    first_name = fields.TextField(analyzer=ngram_analyser)
    last_name = fields.TextField(analyzer=ngram_analyser)
    full_name = fields.TextField(analyzer=ngram_analyser)

    # Common metadata
    slug = fields.KeywordField()

    # Computed fields
    published_datasets_count = fields.IntegerField()
    published_usecases_count = fields.IntegerField()
    members_count = fields.IntegerField()  # Only for organizations
    contributed_sectors_count = fields.IntegerField()

    # For search and filtering
    sectors = fields.TextField(
        attr="sectors_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    def prepare_name(self, instance: Union[Organization, User]) -> str:
        """Prepare name field for indexing."""
        if isinstance(instance, Organization):
            return getattr(instance, "name", "")
        else:  # User
            return getattr(instance, "full_name", "") or getattr(instance, "username", "")

    def prepare_description(self, instance: Union[Organization, User]) -> str:
        """Prepare description field for indexing."""
        if isinstance(instance, Organization):
            return instance.description or ""
        else:  # User
            return instance.bio or ""

    def prepare_publisher_type(self, instance: Union[Organization, User]) -> str:
        """Determine publisher type."""
        return "organization" if isinstance(instance, Organization) else "user"

    def prepare_logo(self, instance: Union[Organization, User]) -> str:
        """Prepare logo/profile picture URL."""
        if isinstance(instance, Organization):
            logo = getattr(instance, "logo", None)
            return str(logo.url) if logo and hasattr(logo, "url") else ""
        else:  # User
            profile_picture = getattr(instance, "profile_picture", None)
            return (
                str(profile_picture.url)
                if profile_picture and hasattr(profile_picture, "url")
                else ""
            )

    def prepare_profile_picture(self, instance: Union[Organization, User]) -> str:
        """Prepare profile picture URL for users."""
        if isinstance(instance, User):
            profile_picture = getattr(instance, "profile_picture", None)
            return (
                str(profile_picture.url)
                if profile_picture and hasattr(profile_picture, "url")
                else ""
            )
        return ""

    def prepare_slug(self, instance: Union[Organization, User]) -> str:
        """Prepare slug field."""
        if isinstance(instance, Organization):
            return getattr(instance, "slug", "") or ""
        else:  # User
            return str(getattr(instance, "id", ""))  # Users don't have slugs, use ID

    def prepare_full_name(self, instance: Union[Organization, User]) -> str:
        """Prepare full name for users."""
        if isinstance(instance, User):
            first_name = getattr(instance, "first_name", "")
            last_name = getattr(instance, "last_name", "")
            if first_name and last_name:
                return f"{first_name} {last_name}"
            elif first_name:
                return first_name
            elif last_name:
                return last_name
            else:
                return getattr(instance, "username", "")
        return ""

    def prepare_published_datasets_count(self, instance: Union[Organization, User]) -> int:
        """Get count of published datasets."""
        try:
            if isinstance(instance, Organization):
                return Dataset.objects.filter(
                    organization_id=instance.id, status=DatasetStatus.PUBLISHED.value
                ).count()
            else:  # User
                return Dataset.objects.filter(
                    user_id=instance.id, status=DatasetStatus.PUBLISHED.value
                ).count()
        except Exception:
            return 0

    def prepare_published_usecases_count(self, instance: Union[Organization, User]) -> int:
        """Get count of published use cases."""
        try:
            if isinstance(instance, Organization):
                from django.db.models import Q

                use_cases = UseCase.objects.filter(
                    (
                        Q(organization__id=instance.id)
                        | Q(usecaseorganizationrelationship__organization_id=instance.id)
                    ),
                    status=UseCaseStatus.PUBLISHED.value,
                ).distinct()
                return use_cases.count()
            else:  # User
                return UseCase.objects.filter(
                    user_id=instance.id, status=UseCaseStatus.PUBLISHED.value
                ).count()
        except Exception:
            return 0

    def prepare_members_count(self, instance: Union[Organization, User]) -> int:
        """Get count of members (only for organizations)."""
        if isinstance(instance, Organization):
            try:
                from authorization.models import OrganizationMembership

                return OrganizationMembership.objects.filter(organization_id=instance.id).count()
            except Exception:
                return 0
        return 0

    def prepare_contributed_sectors_count(self, instance: Union[Organization, User]) -> int:
        """Get count of sectors contributed to."""
        try:
            from api.models import Sector

            if isinstance(instance, Organization):
                # Get sectors from published datasets
                dataset_sectors = (
                    Sector.objects.filter(
                        datasets__organization_id=instance.id,
                        datasets__status=DatasetStatus.PUBLISHED.value,
                    )
                    .values_list("id", flat=True)
                    .distinct()
                )

                # Get sectors from published use cases
                usecase_sectors = (
                    Sector.objects.filter(
                        usecases__usecaseorganizationrelationship__organization_id=instance.id,
                        usecases__status=UseCaseStatus.PUBLISHED.value,
                    )
                    .values_list("id", flat=True)
                    .distinct()
                )
            else:  # User
                # Get sectors from published datasets
                dataset_sectors = (
                    Sector.objects.filter(
                        datasets__user_id=instance.id,
                        datasets__status=DatasetStatus.PUBLISHED.value,
                    )
                    .values_list("id", flat=True)
                    .distinct()
                )

                # Get sectors from published use cases
                usecase_sectors = (
                    Sector.objects.filter(
                        usecases__user_id=instance.id,
                        usecases__status=UseCaseStatus.PUBLISHED.value,
                    )
                    .values_list("id", flat=True)
                    .distinct()
                )

            # Combine and deduplicate sectors
            sector_ids = set(dataset_sectors)
            sector_ids.update(usecase_sectors)

            return len(sector_ids)
        except Exception:
            return 0

    def prepare_sectors_indexing(self, instance: Union[Organization, User]) -> List[str]:
        """Prepare sectors for indexing."""
        try:
            from api.models import Sector

            if isinstance(instance, Organization):
                # Get sectors from published datasets
                dataset_sectors = Sector.objects.filter(
                    datasets__organization_id=instance.id,
                    datasets__status=DatasetStatus.PUBLISHED.value,
                ).distinct()

                # Get sectors from published use cases
                usecase_sectors = Sector.objects.filter(
                    usecases__usecaseorganizationrelationship__organization_id=instance.id,
                    usecases__status=UseCaseStatus.PUBLISHED.value,
                ).distinct()
            else:  # User
                # Get sectors from published datasets
                dataset_sectors = Sector.objects.filter(
                    datasets__user_id=instance.id,
                    datasets__status=DatasetStatus.PUBLISHED.value,
                ).distinct()

                # Get sectors from published use cases
                usecase_sectors = Sector.objects.filter(
                    usecases__user_id=instance.id,
                    usecases__status=UseCaseStatus.PUBLISHED.value,
                ).distinct()

            # Combine and deduplicate sectors
            all_sectors = set(dataset_sectors) | set(usecase_sectors)
            return [
                getattr(sector, "name", "") for sector in all_sectors if hasattr(sector, "name")
            ]
        except Exception:
            return []

    def should_index_object(self, obj: Union[Organization, User]) -> bool:
        """Check if the object should be indexed (has published content)."""
        try:
            if isinstance(obj, Organization):
                has_datasets = Dataset.objects.filter(
                    organization_id=obj.id, status=DatasetStatus.PUBLISHED.value
                ).exists()
                has_usecases = UseCase.objects.filter(
                    organization_id=obj.id, status=UseCaseStatus.PUBLISHED.value
                ).exists()
                return has_datasets or has_usecases
            else:  # User
                has_datasets = Dataset.objects.filter(
                    user_id=obj.id, status=DatasetStatus.PUBLISHED.value
                ).exists()
                has_usecases = UseCase.objects.filter(
                    user_id=obj.id, status=UseCaseStatus.PUBLISHED.value
                ).exists()
                return has_datasets or has_usecases
        except Exception:
            return False

    def get_instances_from_related(
        self,
        related_instance: Union[Dataset, UseCase],
    ) -> Optional[List[Union[Organization, User]]]:
        """Get Publisher instances from related models."""
        publishers: List[Union[Organization, User]] = []

        if isinstance(related_instance, Dataset):
            if related_instance.organization:
                publishers.append(related_instance.organization)
            if related_instance.user:
                publishers.append(related_instance.user)
        elif isinstance(related_instance, UseCase):
            if related_instance.organization:
                publishers.append(related_instance.organization)
            if related_instance.user:
                publishers.append(related_instance.user)

        return publishers if publishers else None


@ORG_INDEX.doc_type
class OrganizationPublisherDocument(PublisherDocument):
    """Organization-specific publisher document."""

    class Django:
        """Django model configuration."""

        model = Organization

        fields = [
            "id",
            "created",
            "modified",
        ]

        related_models = [
            Dataset,
            UseCase,
            Sector,
        ]


@USER_INDEX.doc_type
class UserPublisherDocument(PublisherDocument):
    """User-specific publisher document."""

    class Django:
        """Django model configuration."""

        model = User

        fields = [
            "id",
            "date_joined",
            "last_login",
        ]

        related_models = [
            Dataset,
            UseCase,
            Sector,
        ]

    def prepare_created(self, instance: User) -> Any:
        """Map date_joined to created for consistency."""
        return instance.date_joined

    def prepare_modified(self, instance: User) -> Any:
        """Map last_login to modified for consistency."""
        return instance.last_login
