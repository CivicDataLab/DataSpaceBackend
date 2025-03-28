import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Sector
from api.types.type_sector import TypeSector


@strawberry_django.input(Sector, fields="__all__")
class SectorInput:
    pass


@strawberry_django.partial(Sector, fields="__all__")
class SectorInputPartial:
    id: uuid.UUID
    slug: auto


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


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_sector(self, info: Info, input: SectorInput) -> TypeSector:
        """Create a new sector."""
        # Convert input to a dictionary of field values
        input_dict = {
            f.name: getattr(input, f.name)
            for f in Sector._meta.fields
            if hasattr(input, f.name)
        }
        sector = Sector.objects.create(**input_dict)
        return TypeSector.from_django(sector)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_sector(
        self, info: Info, input: SectorInputPartial
    ) -> Optional[TypeSector]:
        """Update an existing sector."""
        try:
            sector = Sector.objects.get(id=input.id)

            # Convert input to a dictionary of field values, excluding id
            input_dict = {
                f.name: getattr(input, f.name)
                for f in Sector._meta.fields
                if hasattr(input, f.name) and f.name != "id"
            }

            # Update the sector with the provided fields
            for field, value in input_dict.items():
                setattr(sector, field, value)
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
