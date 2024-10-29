import datetime
import uuid

import strawberry
import strawberry_django
from strawberry_django.mutations import mutations

from api.models import ResourceChartImage, Dataset
from api.types.type_resource_chart_image import TypeResourceChartImage


@strawberry_django.input(ResourceChartImage, fields="__all__", exclude=["datasets", "slug"])
class ResourceChartImageInput:
    pass


@strawberry_django.partial(ResourceChartImage, fields="__all__", exclude=["datasets"])
class ResourceChartImageInputPartial:
    id: str


@strawberry.type(name="Query")
class Query:
    resource_chart_images: list[TypeResourceChartImage] = strawberry_django.field()
    @strawberry_django.field
    def dataset_resource_charts(self, info, dataset_id: uuid.UUID) -> list[TypeResourceChartImage]:
        return ResourceChartImage.objects.filter(dataset_id=dataset_id)


@strawberry.type
class Mutation:
    create_resource_chart_image: TypeResourceChartImage = mutations.create(ResourceChartImageInput)
    update_resource_chart_image: TypeResourceChartImage = mutations.update(ResourceChartImageInputPartial,
                                                                           key_attr="id")

    @strawberry_django.mutation(handle_django_errors=True)
    def add_resource_chart_image(self, info, dataset: uuid.UUID) -> TypeResourceChartImage:
        try:
            dataset = Dataset.objects.get(id=dataset)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset} does not exist.")
        resource_chart_image: ResourceChartImage = ResourceChartImage()
        now = datetime.datetime.now()
        resource_chart_image.name = f"New resource_chart_image {now.strftime('%d %b %Y - %H:%M')}"
        resource_chart_image.dataset = dataset
        resource_chart_image.save()
        return resource_chart_image

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_resource_chart_image(self, resource_chart_image_id: str) -> bool:
        try:
            resource_chart_image = ResourceChartImage.objects.get(id=resource_chart_image_id)
        except ResourceChartImage.DoesNotExist as e:
            raise ValueError(f"ResourceChartImage with ID {resource_chart_image_id} does not exist.")
        resource_chart_image.delete()
        return True
