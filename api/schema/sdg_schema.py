import uuid
from typing import Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models import SDG
from api.types.type_sdg import SDGFilter, SDGOrder, TypeSDG


@strawberry.input
class SDGInput:
    name: str
    code: str
    description: Optional[str] = None


@strawberry_django.partial(SDG)
class SDGInputPartial:
    id: uuid.UUID
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None


@strawberry.type(name="Query")
class Query:
    sdgs: list[TypeSDG] = strawberry_django.field()

    @strawberry_django.field
    def sdg(self, info: Info, id: uuid.UUID) -> Optional[TypeSDG]:
        """Get SDG by ID."""
        try:
            sdg = SDG.objects.get(id=id)
            return TypeSDG.from_django(sdg)
        except SDG.DoesNotExist:
            raise ValueError(f"SDG with ID {id} does not exist.")

    @strawberry_django.field(
        filters=SDGFilter,
        pagination=True,
        order=SDGOrder,
    )
    def all_sdgs(
        self,
        info: Info,
        filters: Optional[SDGFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[SDGOrder] = strawberry.UNSET,
    ) -> list[TypeSDG]:
        """Get all SDGs."""
        queryset = SDG.objects.all()

        # Apply filters if provided
        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        # Apply ordering if provided
        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        # Apply pagination if provided
        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return [TypeSDG.from_django(instance) for instance in queryset]


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_sdg(self, info: Info, input: SDGInput) -> TypeSDG:
        """Create a new SDG."""
        sdg = SDG(
            name=input.name,
            code=input.code,
            description=input.description,
        )
        sdg.save()
        return TypeSDG.from_django(sdg)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_sdg(self, info: Info, input: SDGInputPartial) -> Optional[TypeSDG]:
        """Update an existing SDG."""
        try:
            sdg = SDG.objects.get(id=input.id)

            # Update fields if provided
            if input.name is not None:
                sdg.name = input.name
            if input.code is not None:
                sdg.code = input.code
            if input.description is not None:
                sdg.description = input.description
            if input.slug is not None:
                sdg.slug = input.slug

            sdg.save()
            return TypeSDG.from_django(sdg)
        except SDG.DoesNotExist:
            raise ValueError(f"SDG with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_sdg(self, info: Info, sdg_id: uuid.UUID) -> bool:
        """Delete an SDG."""
        try:
            sdg = SDG.objects.get(id=sdg_id)
            sdg.delete()
            return True
        except SDG.DoesNotExist:
            raise ValueError(f"SDG with ID {sdg_id} does not exist.")
