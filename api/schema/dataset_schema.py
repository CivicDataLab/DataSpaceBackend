import uuid
from typing import List, Optional

import strawberry
import strawberry_django

from api import types, models
from api.enums import DatasetStatus
from api.models import Dataset, Metadata
from api.models.Dataset import Tag
from api.models.DatasetMetadata import DatasetMetadata


@strawberry.input
class DSMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateMetadataInput:
    dataset: uuid.UUID
    metadata: List[DSMetadataItemType]


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
            # TODO: apply validations from metadata validations
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


@strawberry.type
class Mutation:
    # @strawberry_django.input_mutation()
    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset(self) -> types.TypeDataset:
        # TODO: capture organisation
        dataset: Dataset = models.Dataset()
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

        _add_update_dataset_metadata(dataset, metadata_input)
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
        dataset.status = DatasetStatus.PUBLISHED
        dataset.save()
        return dataset
