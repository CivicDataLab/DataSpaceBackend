import datetime
import uuid
from typing import List, Optional, Union

import strawberry
import strawberry_django
from strawberry_django.pagination import OffsetPaginationInput

from api import types, models
from api.models import Dataset, Metadata, Category, ResourceChartImage, Resource, ResourceChartDetails
from api.models.Dataset import Tag
from api.models.DatasetMetadata import DatasetMetadata
from api.types import TypeDataset, TypeResourceChart
from api.types.type_dataset import DatasetFilter, DatasetOrder
from api.types.type_resource_chart_image import TypeResourceChartImage
from api.utils.enums import DatasetStatus


@strawberry.input
class DSMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateMetadataInput:
    dataset: uuid.UUID
    metadata: List[DSMetadataItemType]
    description: Optional[str]
    tags: Optional[List[str]]
    categories: List[uuid.UUID]


@strawberry.input
class UpdateDatasetInput:
    dataset: uuid.UUID
    title: Optional[str]
    description: Optional[str]
    tags: List[str]


def _add_update_dataset_metadata(dataset: Dataset, metadata_input: List[DSMetadataItemType]):
    if not metadata_input or len(metadata_input) == 0:
        return
    _delete_existing_metadata(dataset)
    for metadata_input_item in metadata_input:
        try:
            metadata_field = Metadata.objects.get(id=metadata_input_item.id)
            if not metadata_field.enabled:
                _delete_existing_metadata(dataset)
                raise ValueError(f"Metadata with ID {metadata_input_item.id} is not enabled.")
            ds_metadata = DatasetMetadata(dataset=dataset, metadata_item=metadata_field,
                                          value=metadata_input_item.value)
            ds_metadata.save()
        except Metadata.DoesNotExist as e:
            _delete_existing_metadata(dataset)
            raise ValueError(f"Metadata with ID {metadata_input_item.id} does not exist.")


def _update_dataset_tags(dataset: Dataset, tags: List[str]):
    dataset.tags.clear()
    for tag in tags:
        dataset.tags.add(Tag.objects.get_or_create(defaults={'value': tag}, value__iexact=tag)[0])
    dataset.save()


def _delete_existing_metadata(dataset):
    try:
        existing_metadata = DatasetMetadata.objects.filter(dataset=dataset)
        existing_metadata.delete()
    except DatasetMetadata.DoesNotExist as e:
        pass


def _add_update_dataset_categories(dataset: Dataset, categories: list[uuid.UUID]):
    categories = Category.objects.filter(id__in=categories)
    dataset.categories.clear()
    dataset.categories.add(*categories)
    dataset.save()


@strawberry.type
class Query:
    @strawberry_django.field(filters=DatasetFilter, pagination=True, order=DatasetOrder)
    def datasets(self, info,
                 filters: DatasetFilter | None = strawberry.UNSET,
                 pagination: OffsetPaginationInput | None = strawberry.UNSET,
                 order: DatasetOrder | None = strawberry.UNSET) -> List[TypeDataset]:
        organization = info.context.request.context.get('organization')
        dataspace = info.context.request.context.get('dataspace')

        # Base queryset filtering by organization or dataspace
        if dataspace:
            queryset = Dataset.objects.filter(dataspace=dataspace)
        elif organization:
            queryset = Dataset.objects.filter(organization=organization)
        else:
            queryset = Dataset.objects.all()

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset, info)

        return queryset

    @strawberry.mutation
    def get_chart_data(self, dataset_id: uuid.UUID) -> List[Union[TypeResourceChartImage, TypeResourceChart]]:
        # Fetch ResourceChartImage for the dataset
        chart_images = list(ResourceChartImage.objects.filter(dataset_id=dataset_id).order_by("modified"))

        # Fetch ResourceChartDetails based on the related Resource in the same dataset
        resource_ids = Resource.objects.filter(dataset_id=dataset_id).values_list('id', flat=True)
        chart_details = list(ResourceChartDetails.objects.filter(resource_id__in=resource_ids).order_by("modified"))

        # Combine both chart_images and chart_details into a single list
        combined_list = chart_images + chart_details

        # Sort the combined list by the 'modified' field in descending order
        sorted_list = sorted(combined_list, key=lambda x: x.modified, reverse=True)

        return sorted_list


@strawberry.type
class Mutation:
    # @strawberry_django.input_mutation()
    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset(self, info) -> types.TypeDataset:
        dataset: Dataset = models.Dataset()
        dataset.organization = info.context.request.context.get('organization')
        dataset.dataspace = info.context.request.context.get('dataspace')
        now = datetime.datetime.now()
        dataset.title = f"New dataset {now.strftime('%d %b %Y - %H:%M')}"
        # sync_to_async(dataset.save)()
        dataset.save()
        return dataset

    @strawberry_django.mutation(handle_django_errors=True)
    def add_update_dataset_metadata(self, update_metadata_input: UpdateMetadataInput) -> types.TypeDataset:
        dataset_id = update_metadata_input.dataset
        metadata_input = update_metadata_input.metadata
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        if update_metadata_input.description:
            dataset.description = update_metadata_input.description
            dataset.save()
        if update_metadata_input.tags:
            _update_dataset_tags(dataset, update_metadata_input.tags)
        _add_update_dataset_metadata(dataset, metadata_input)
        _add_update_dataset_categories(dataset, update_metadata_input.categories)
        print(update_metadata_input)
        return dataset

    @strawberry_django.mutation(handle_django_errors=True)
    def update_dataset(self, update_dataset_input: UpdateDatasetInput) -> types.TypeDataset:
        dataset_id = update_dataset_input.dataset
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        if update_dataset_input.title:
            dataset.title = update_dataset_input.title
        if update_dataset_input.description:
            dataset.description = update_dataset_input.description
        _update_dataset_tags(dataset, update_dataset_input.tags)
        return dataset

    @strawberry_django.mutation(handle_django_errors=True)
    def publish_dataset(self, dataset_id: uuid.UUID) -> types.TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        # TODO: validate dataset
        dataset.status = DatasetStatus.PUBLISHED.value
        dataset.save()
        return dataset

    @strawberry_django.mutation(handle_django_errors=True)
    def un_publish_dataset(self, dataset_id: uuid.UUID) -> types.TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        # TODO: validate dataset
        dataset.status = DatasetStatus.DRAFT
        dataset.save()
        return dataset

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_dataset(self, dataset_id: uuid.UUID) -> bool:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        dataset.delete()
        return True
