import uuid
from typing import List

import strawberry
import strawberry_django
# from asgiref.sync import sync_to_async

from api import types, models, validators
from api.models import Dataset, Metadata
from api.models.DatasetMetadata import DatasetMetadata
from api.validators import DateValidator, LinkValidator, NameValidators
from api.enums import MetadataValidators
from django.core.exceptions import ValidationError

@strawberry.input
class DSMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateMetadataInput:
    dataset: uuid.UUID
    metadata: List[DSMetadataItemType]

# define dictory with all the validators
dict_validators = {
    MetadataValidators.DateValidator: DateValidator,
    MetadataValidators.LinkValidator: LinkValidator,
    MetadataValidators.NameValidator: NameValidators
}

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
            try:
                validator_function = dict_validators[metadata_field.validator]
                validator_function(metadata_input_item.value)  # Validate the actual value
            except KeyError:
                    print(f"No validator named '{metadata_field.validator}' found in the dictionary.")
                    raise ValueError(f"No validator named '{metadata_field.validator}' found.")
            except ValidationError as e:
                    print(f"Validation error for {metadata_field.validator}: {e}")
                    raise ValueError(f"Validation error: {e}")
            except Exception as e:
                    print(f"Error occurred while validating {metadata_field.validator}: {e}")
                    raise ValueError(f"Error occurred while validating: {e}")

            ds_metadata.save()
        except Metadata.DoesNotExist as e:
            _delete_existing_metadata(dataset)
            raise ValueError(f"Metadata with ID {metadata_input_item.id} does not exist.")


def _delete_existing_metadata(dataset):
    try:
        existing_metadata = DatasetMetadata.objects.get(dataset=dataset)
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

        # Verify if dataset exists
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        _add_update_dataset_metadata(dataset, metadata_input)
        print(update_metadata_input)
        return dataset
