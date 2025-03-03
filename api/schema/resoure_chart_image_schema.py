import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Dataset, ResourceChartImage
from api.types.type_resource_chart_image import TypeResourceChartImage


@strawberry_django.input(
    ResourceChartImage, fields="__all__", exclude=["datasets", "slug"]
)
class ResourceChartImageInput:
    pass


@strawberry_django.partial(ResourceChartImage, fields="__all__", exclude=["datasets"])
class ResourceChartImageInputPartial:
    id: uuid.UUID


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field(pagination=True)
    def resource_chart_images(self, info: Info) -> List[TypeResourceChartImage]:
        """Get all resource chart images."""
        images = ResourceChartImage.objects.all()
        return [TypeResourceChartImage.from_django(image) for image in images]

    @strawberry_django.field(pagination=True)
    def dataset_resource_charts(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeResourceChartImage]:
        """Get all resource chart images for a dataset."""
        images = ResourceChartImage.objects.filter(dataset_id=dataset_id)
        return [TypeResourceChartImage.from_django(image) for image in images]


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_resource_chart_image(
        self, info: Info, input: ResourceChartImageInput
    ) -> TypeResourceChartImage:
        """Create a new resource chart image."""
        image = mutations.create(ResourceChartImageInput)(info=info, input=input)
        return TypeResourceChartImage.from_django(image)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_resource_chart_image(
        self, info: Info, input: ResourceChartImageInputPartial
    ) -> TypeResourceChartImage:
        """Update an existing resource chart image."""
        image = mutations.update(ResourceChartImageInputPartial, key_attr="id")(
            info=info, input=input
        )
        return TypeResourceChartImage.from_django(image)

    @strawberry_django.mutation(handle_django_errors=True)
    def add_resource_chart_image(
        self, info: Info, dataset: uuid.UUID
    ) -> TypeResourceChartImage:
        """Add a new resource chart image to a dataset."""
        try:
            dataset_obj = Dataset.objects.get(id=dataset)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset} does not exist.")

        now = datetime.datetime.now()
        image = ResourceChartImage.objects.create(
            name=f"New resource_chart_image {now.strftime('%d %b %Y - %H:%M')}",
            dataset=dataset_obj,
        )
        return TypeResourceChartImage.from_django(image)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_resource_chart_image(
        self, info: Info, resource_chart_image_id: uuid.UUID
    ) -> bool:
        """Delete a resource chart image."""
        try:
            image = ResourceChartImage.objects.get(id=resource_chart_image_id)
            image.delete()
            return True
        except ResourceChartImage.DoesNotExist:
            raise ValueError(
                f"ResourceChartImage with ID {resource_chart_image_id} does not exist."
            )
