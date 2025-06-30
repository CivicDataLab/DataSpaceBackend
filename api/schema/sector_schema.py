import uuid
from typing import Any, List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations
from strawberry_django.pagination import OffsetPaginationInput

from api.models import Sector
from api.types.type_sector import SectorFilter, SectorOrder, TypeSector
from api.utils.enums import DatasetStatus


@strawberry.input
class SectorInput:
    name: str
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


@strawberry_django.partial(Sector)
class SectorInputPartial:
    id: uuid.UUID
    name: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


@strawberry.type(name="Query")
class Query:
    sectors: list[TypeSector] = strawberry_django.field()

    @strawberry_django.field
    def sector(self, info: Info, id: uuid.UUID) -> Optional[TypeSector]:
        """Get sector by ID."""
        try:
            sector = Sector.objects.get(id=id)
            return TypeSector.from_django(sector)
        except Sector.DoesNotExist:
            raise ValueError(f"Sector with ID {id} does not exist.")

    @strawberry_django.field(
        filters=SectorFilter,
        pagination=True,
        order=SectorOrder,
    )
    def active_sectors(
        self,
        info: Info,
        filters: Optional[SectorFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[SectorOrder] = strawberry.UNSET,
    ) -> list[TypeSector]:
        """Get sectors with published datasets."""
        # Start with base queryset filtering for active sectors
        queryset = Sector.objects.filter(
            datasets__status=DatasetStatus.PUBLISHED
        ).distinct()

        # Apply filters if provided
        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        # Apply ordering if provided
        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        # Apply pagination if provided
        if pagination is not strawberry.UNSET:
            # Apply pagination to the list
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return [TypeSector.from_django(instance) for instance in queryset]


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_sector(self, info: Info, input: SectorInput) -> TypeSector:
        """Create a new sector."""
        # Create a new sector with the provided name and description
        sector = Sector(
            name=input.name,
            description=input.description,
        )

        # Handle parent_id if provided
        if input.parent_id is not None:
            try:
                parent_sector = Sector.objects.get(id=input.parent_id)
                sector.parent_id = parent_sector
            except Sector.DoesNotExist:
                raise ValueError(
                    f"Parent sector with ID {input.parent_id} does not exist."
                )

        # Save the sector to generate the slug
        sector.save()

        return TypeSector.from_django(sector)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_sector(
        self, info: Info, input: SectorInputPartial
    ) -> Optional[TypeSector]:
        """Update an existing sector."""
        try:
            sector = Sector.objects.get(id=input.id)

            # Get the fields to update, excluding id and parent_id (handle separately)
            input_dict = {
                f.name: getattr(input, f.name)
                for f in Sector._meta.fields
                if hasattr(input, f.name) and f.name not in ["id", "parent_id"]
            }

            # Update the sector with the provided fields
            for field, value in input_dict.items():
                if value is not None:
                    setattr(sector, field, value)

            # Handle parent_id separately if it's provided
            if hasattr(input, "parent_id") and input.parent_id is not None:
                try:
                    parent_sector = Sector.objects.get(id=input.parent_id)
                    sector.parent_id = parent_sector
                except Sector.DoesNotExist:
                    raise ValueError(
                        f"Parent sector with ID {input.parent_id} does not exist."
                    )

            sector.save()

            return TypeSector.from_django(sector)
        except Sector.DoesNotExist:
            raise ValueError(f"Sector with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_sector(self, info: Info, sector_id: uuid.UUID) -> bool:
        """Delete a sector."""
        try:
            sector = Sector.objects.get(id=sector_id)
            sector.delete()
            return True
        except Sector.DoesNotExist:
            raise ValueError(f"Sector with ID {sector_id} does not exist.")
