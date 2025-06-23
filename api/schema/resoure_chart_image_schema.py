import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.file_uploads import Upload
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Dataset, ResourceChartImage
from api.types.type_resource_chart_image import TypeResourceChartImage
from api.utils.enums import ChartStatus


@strawberry_django.input(
    ResourceChartImage, fields="__all__", exclude=["datasets", "modified", "status"]
)
class ResourceChartImageInput:
    dataset: uuid.UUID
    image: Optional[Upload] = strawberry.field(default=None)
    name: Optional[str] = strawberry.field(default=None)


@strawberry_django.partial(
    ResourceChartImage, fields="__all__", exclude=["datasets", "modified", "status"]
)
class ResourceChartImageInputPartial:
    id: uuid.UUID
    dataset: uuid.UUID
    image: Optional[Upload] = strawberry.field(default=None)
    name: Optional[str] = strawberry.field(default=None)


@strawberry.type(name="Query")
class Query:
    resource_chart_images: list[TypeResourceChartImage] = strawberry_django.field()

    @strawberry_django.field(pagination=True)
    def dataset_resource_charts(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeResourceChartImage]:
        """Get all resource chart images for a dataset."""
        images = ResourceChartImage.objects.filter(dataset_id=dataset_id)
        return [TypeResourceChartImage.from_django(image) for image in images]

    @strawberry_django.field
    def resource_chart_image(
        self, info: Info, image_id: uuid.UUID
    ) -> TypeResourceChartImage:
        try:
            image = ResourceChartImage.objects.get(id=image_id)
            return TypeResourceChartImage.from_django(image)
        except ResourceChartImage.DoesNotExist as e:
            raise ValueError(f"Resource Chart Image with ID {image_id} does not exist.")


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_resource_chart_image(
        self, info: Info, input: ResourceChartImageInput
    ) -> TypeResourceChartImage:
        """Create a new resource chart image."""
        try:
            dataset_obj = Dataset.objects.get(id=input.dataset)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {input.dataset} does not exist.")
        now = datetime.datetime.now()
        image = ResourceChartImage.objects.create(
            name=input.name
            or f"New resource_chart_image {now.strftime('%d %b %Y - %H:%M:%S')}",
            dataset=dataset_obj,
            image=input.image,
        )
        return TypeResourceChartImage.from_django(image)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_resource_chart_image(
        self, info: Info, input: ResourceChartImageInputPartial
    ) -> TypeResourceChartImage:
        """Update an existing resource chart image."""
        try:
            image = ResourceChartImage.objects.get(id=input.id)
        except ResourceChartImage.DoesNotExist:
            raise ValueError(f"ResourceChartImage with ID {input.id} does not exist.")
        try:
            dataset_obj = Dataset.objects.get(id=input.dataset)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {input.dataset} does not exist.")
        if input.name:
            image.name = input.name
        if input.image:
            image.image = input.image
        image.dataset = dataset_obj
        image.save()
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
            name=f"New resource_chart_image {now.strftime('%d %b %Y - %H:%M:%S')}",
            dataset=dataset_obj,
        )
        return TypeResourceChartImage.from_django(image)

    @strawberry_django.mutation(handle_django_errors=False)
    def publish_resource_chart_image(
        self, info: Info, resource_chart_image_id: uuid.UUID
    ) -> bool:
        try:
            image = ResourceChartImage.objects.get(id=resource_chart_image_id)
            image.status = ChartStatus.PUBLISHED
            image.save()
            return True
        except ResourceChartImage.DoesNotExist as e:
            raise ValueError(
                f"Resource Chart Image with ID {resource_chart_image_id} does not exist."
            )

    @strawberry_django.mutation(handle_django_errors=False)
    def unpublish_resource_chart_image(
        self, info: Info, resource_chart_image_id: uuid.UUID
    ) -> bool:
        try:
            image = ResourceChartImage.objects.get(id=resource_chart_image_id)
            image.status = ChartStatus.DRAFT
            image.save()
            return True
        except ResourceChartImage.DoesNotExist as e:
            raise ValueError(
                f"Resource Chart Image with ID {resource_chart_image_id} does not exist."
            )

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
