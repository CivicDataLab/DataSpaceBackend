from typing import Optional

import strawberry
import strawberry_django
from strawberry.file_uploads import Upload
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models import ExternalContributor
from api.services.external_contributor_service import is_email_already_user
from api.types.type_external_contributor import ExternalContributorFilter, ExternalContributorOrder, TypeExternalContributor


@strawberry.input
class ExternalContributorInput:
    name: str
    email: str
    designation: Optional[str] = None
    bio: Optional[str] = None
    image: Optional[Upload] = None


@strawberry_django.partial(ExternalContributor)
class ExternalContributorInputPartial:
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    bio: Optional[str] = None
    image: Optional[Upload] = None
    has_approved: Optional[bool] = None


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def external_contributor(self, info: Info, id: int) -> Optional[TypeExternalContributor]:
        """Get an external contributor by ID."""
        try:
            external_contributor = ExternalContributor.objects.get(id=id)
            return TypeExternalContributor.from_django(external_contributor)
        except ExternalContributor.DoesNotExist:
            raise ValueError(f"External contributor with ID {id} does not exist.")

    @strawberry_django.field(
        filters=ExternalContributorFilter,
        pagination=True,
        order=ExternalContributorOrder,
    )
    def external_contributors(
        self,
        info: Info,
        filters: Optional[ExternalContributorFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[ExternalContributorOrder] = strawberry.UNSET,
    ) -> list[TypeExternalContributor]:
        """Get all external contributors with optional filters, pagination, and ordering."""
        queryset = ExternalContributor.objects.all()

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return [TypeExternalContributor.from_django(instance) for instance in queryset]

    @strawberry_django.field(pagination=True)
    def search_external_contributors(
        self,
        info: Info,
        query: str,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
    ) -> list[TypeExternalContributor]:
        """Search external contributors by name or email (minimum 3 characters)."""
        query_clean = query.strip()

        if len(query_clean) < 3:
            raise ValueError("Search query must be at least 3 characters long.")

        queryset = ExternalContributor.objects.filter(
            name__icontains=query_clean
        ) | ExternalContributor.objects.filter(email__icontains=query_clean)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return [TypeExternalContributor.from_django(instance) for instance in queryset]


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_external_contributor(self, info: Info, input: ExternalContributorInput) -> TypeExternalContributor:
        """Create a new external contributor."""
        email_lower = input.email.lower().strip()

        if ExternalContributor.objects.filter(email__iexact=email_lower).exists():
            raise ValueError(f"An external contributor with email '{input.email}' already exists.")

        if is_email_already_user(email_lower):
            raise ValueError(
                f"Email '{input.email}' is already registered as a user on the platform. "
                "Please use that account instead."
            )

        external_contributor = ExternalContributor(
            name=input.name,
            email=email_lower,
            designation=input.designation,
            bio=input.bio,
            has_approved=True,  # Set to True when creating via mutation
        )

        if input.image is not None:
            external_contributor.image = input.image

        external_contributor.save()

        return TypeExternalContributor.from_django(external_contributor)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_external_contributor(
        self, info: Info, input: ExternalContributorInputPartial
    ) -> Optional[TypeExternalContributor]:
        """Update an existing external contributor."""
        try:
            external_contributor = ExternalContributor.objects.get(id=input.id)

            # Check for duplicate email if email is being updated
            if input.email is not None:
                email_lower = input.email.lower().strip()
                if (
                    ExternalContributor.objects.filter(email__iexact=email_lower)
                    .exclude(id=input.id)
                    .exists()
                ):
                    raise ValueError(f"An external contributor with email '{input.email}' already exists.")
                if is_email_already_user(email_lower):
                    raise ValueError(
                        f"Email '{input.email}' is already registered as a user on the platform. "
                        "Please use that account instead."
                    )
                external_contributor.email = email_lower

            if input.name is not None:
                external_contributor.name = input.name

            if input.designation is not None:
                external_contributor.designation = input.designation

            if input.bio is not None:
                external_contributor.bio = input.bio

            if input.image is not None:
                external_contributor.image = input.image

            if input.has_approved is not None:
                external_contributor.has_approved = input.has_approved

            external_contributor.save()

            return TypeExternalContributor.from_django(external_contributor)
        except ExternalContributor.DoesNotExist:
            raise ValueError(f"External contributor with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_external_contributor(self, info: Info, external_contributor_id: int) -> bool:
        """Delete an external contributor."""
        try:
            external_contributor = ExternalContributor.objects.get(id=external_contributor_id)
            external_contributor.delete()
            return True
        except ExternalContributor.DoesNotExist:
            raise ValueError(f"External contributor with ID {external_contributor_id} does not exist.")
