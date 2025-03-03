import unittest
import uuid
from typing import List, Optional
from unittest.mock import Mock, patch

from api.models import Dataset, Metadata
from api.models.DatasetMetadata import DatasetMetadata
from api.schema.dataset_schema import DSMetadataItemType, _add_update_dataset_metadata


class TestAddUpdateDatasetMetadata(unittest.TestCase):
    """Test cases for _add_update_dataset_metadata function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.dataset_id = uuid.uuid4()
        self.dataset: Mock = Mock(spec=Dataset, id=self.dataset_id)

    @patch("api.schema.dataset_schema.Dataset.objects.create")
    @patch("api.schema.dataset_schema.Metadata.objects.get")
    def test_add_new_metadata(
        self, mock_metadata_get: Mock, mock_dataset_create: Mock
    ) -> None:
        """Test adding new metadata to a dataset."""
        mock_dataset_create.return_value = self.dataset
        mock_metadata_get.return_value = Mock(spec=Metadata, enabled=True)

        metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="1", value="Value 1"),
            DSMetadataItemType(id="2", value="Value 2"),
        ]

        with patch(
            "api.schema.dataset_schema._delete_existing_metadata"
        ) as mock_delete:
            _add_update_dataset_metadata(self.dataset, metadata_input)
            mock_delete.assert_called_once_with(self.dataset)

        mock_dataset_create.assert_called_once()
        mock_metadata_get.assert_any_call(id="1")
        mock_metadata_get.assert_any_call(id="2")

        self.assertEqual(self.dataset.datasetmetadata_set.count(), 2)

    @patch("api.schema.dataset_schema.Dataset.objects.create")
    @patch("api.schema.dataset_schema.Metadata.objects.get")
    def test_update_existing_metadata(
        self, mock_metadata_get: Mock, mock_dataset_create: Mock
    ) -> None:
        """Test updating existing metadata in a dataset."""
        mock_dataset_create.return_value = self.dataset
        mock_metadata_get.return_value = Mock(spec=Metadata, enabled=True)

        metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="1", value="Value 1"),
            DSMetadataItemType(id="2", value="Value 2"),
        ]
        _add_update_dataset_metadata(self.dataset, metadata_input)

        updated_metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="1", value="Updated Value 1"),
            DSMetadataItemType(id="2", value="Updated Value 2"),
        ]
        _add_update_dataset_metadata(self.dataset, updated_metadata_input)

        mock_dataset_create.assert_called_once()
        mock_metadata_get.assert_any_call(id="1")
        mock_metadata_get.assert_any_call(id="2")

        self.assertEqual(self.dataset.datasetmetadata_set.count(), 2)

    @patch("api.schema.dataset_schema.Dataset.objects.create")
    @patch("api.schema.dataset_schema.Metadata.objects.get")
    def test_delete_existing_metadata(
        self, mock_metadata_get: Mock, mock_dataset_create: Mock
    ) -> None:
        """Test deleting existing metadata from a dataset."""
        mock_dataset_create.return_value = self.dataset
        mock_metadata_get.return_value = Mock(spec=Metadata, enabled=True)

        metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="1", value="Value 1"),
            DSMetadataItemType(id="2", value="Value 2"),
        ]
        _add_update_dataset_metadata(self.dataset, metadata_input)
        self.assertEqual(self.dataset.datasetmetadata_set.count(), 2)

        with patch(
            "api.schema.dataset_schema._delete_existing_metadata"
        ) as mock_delete:
            _add_update_dataset_metadata(self.dataset, [])
            mock_delete.assert_called_once_with(self.dataset)

        self.assertEqual(self.dataset.datasetmetadata_set.count(), 0)

    @patch("api.schema.dataset_schema.Dataset.objects.create")
    @patch("api.schema.dataset_schema.Metadata.objects.get")
    def test_handle_non_existent_metadata_id(
        self, mock_metadata_get: Mock, mock_dataset_create: Mock
    ) -> None:
        """Test handling non-existent metadata ID."""
        mock_dataset_create.return_value = self.dataset
        mock_metadata_get.side_effect = Metadata.DoesNotExist

        metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="non-existent-id", value="Value 1"),
        ]

        with self.assertRaises(ValueError) as context:
            _add_update_dataset_metadata(self.dataset, metadata_input)

        self.assertEqual(
            str(context.exception), "Metadata with ID non-existent-id does not exist."
        )

    @patch("api.schema.dataset_schema.Dataset.objects.create")
    @patch("api.schema.dataset_schema.Metadata.objects.get")
    def test_handle_disabled_metadata_field(
        self, mock_metadata_get: Mock, mock_dataset_create: Mock
    ) -> None:
        """Test handling disabled metadata field."""
        mock_dataset_create.return_value = self.dataset
        mock_metadata_get.return_value = Mock(spec=Metadata, enabled=False)

        metadata_input: List[DSMetadataItemType] = [
            DSMetadataItemType(id="1", value="Value 1"),
        ]

        with self.assertRaises(ValueError) as context:
            _add_update_dataset_metadata(self.dataset, metadata_input)

        self.assertEqual(str(context.exception), "Metadata with ID 1 is not enabled.")
