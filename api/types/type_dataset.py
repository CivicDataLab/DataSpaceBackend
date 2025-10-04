import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, cast

import strawberry
import strawberry_django
import structlog
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import Dataset, DatasetMetadata, Resource, Tag
from api.types.base_type import BaseType
from api.types.type_dataset_metadata import TypeDatasetMetadata
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_resource import TypeResource
from api.types.type_sector import TypeSector
from api.utils.enums import DatasetStatus
from authorization.types import TypeUser

logger = structlog.get_logger("dataspace.type_dataset")

dataset_status: EnumType = strawberry.enum(DatasetStatus)  # type: ignore


@strawberry_django.filter(Dataset)
class DatasetFilter:
    """Filter for dataset."""

    id: Optional[uuid.UUID]
    status: Optional[dataset_status]


@strawberry_django.order(Dataset)
class DatasetOrder:
    """Order for dataset."""

    title: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto


@strawberry_django.type(
    Dataset,
    fields="__all__",
    filters=DatasetFilter,
    pagination=True,
    order=DatasetOrder,  # type: ignore
)
class TypeDataset(BaseType):
    """Type for dataset."""

    id: uuid.UUID
    title: str
    description: Optional[str]
    slug: str
    status: dataset_status
    organization: Optional["TypeOrganization"]
    created: datetime
    modified: datetime
    tags: List["TypeTag"]
    download_count: int
    user: Optional["TypeUser"]

    @strawberry.field
    def sectors(self, info: Info) -> List["TypeSector"]:
        """Get sectors for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeSector]: List of sectors
        """
        try:
            django_instance = cast(Dataset, self)
            queryset = django_instance.sectors.all()
            return TypeSector.from_django_list(queryset)
        except (AttributeError, Dataset.DoesNotExist):
            return []

    @strawberry.field
    def geographies(self, info: Info) -> List["TypeGeo"]:
        """Get geographies for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeGeo]: List of geographies
        """
        try:
            from api.types.type_geo import TypeGeo

            django_instance = cast(Dataset, self)
            queryset = django_instance.geographies.all()
            return TypeGeo.from_django_list(queryset)
        except (AttributeError, Dataset.DoesNotExist):
            return []

    @strawberry.field
    def metadata(self) -> List["TypeDatasetMetadata"]:
        """Get metadata for this dataset."""
        try:
            queryset = DatasetMetadata.objects.filter(dataset_id=self.id)
            return TypeDatasetMetadata.from_django_list(queryset)
        except (AttributeError, DatasetMetadata.DoesNotExist):
            return []

    @strawberry.field
    def resources(self) -> List["TypeResource"]:
        """Get resources for this dataset."""
        try:
            queryset = Resource.objects.filter(dataset_id=self.id)
            return TypeResource.from_django_list(queryset)
        except (AttributeError, Resource.DoesNotExist):
            return []

    @strawberry.field
    def formats(self: Any) -> List[str]:
        """Get formats for this dataset."""
        try:
            # Get all format values and filter out None values
            formats = Resource.objects.filter(dataset_id=self.id).values_list(
                "resourcefiledetails__format", flat=True
            )
            # Filter out None values and return as list
            return [fmt for fmt in formats if fmt is not None]
        except (AttributeError, Resource.DoesNotExist):
            return []

    @strawberry.field(
        description="Get similar datasets for this dataset from elasticsearch index."
    )
    def similar_datasets(self: Any) -> List["TypeDataset"]:  # type: ignore
        """Get similar datasets for this dataset from elasticsearch index."""
        try:
            from elasticsearch_dsl import Q as ESQ
            from elasticsearch_dsl import Search

            from search.documents import DatasetDocument

            # Get the current dataset
            dataset = Dataset.objects.get(id=self.id)

            # Create a search query
            search = Search(index=DatasetDocument._index._name)

            # Build a query to find similar datasets
            should_queries = []

            # Add title similarity
            if dataset.title:
                should_queries.append(
                    ESQ(
                        "match",
                        title={
                            "query": dataset.title,
                            "boost": 3.0,  # Give higher weight to title matches
                        },
                    )
                )

            # Add description similarity
            if dataset.description:
                should_queries.append(
                    ESQ(
                        "match",
                        description={"query": dataset.description, "boost": 2.0},
                    )
                )

            # Add tags similarity
            from api.models import Tag

            tags = [tag.value for tag in dataset.tags.all().select_related()]  # type: ignore
            if tags:
                should_queries.append(ESQ("terms", **{"tags.raw": tags, "boost": 2.5}))

            # Add sectors similarity
            from api.models import Sector

            sectors = [sector.name for sector in dataset.sectors.all().select_related()]  # type: ignore
            if sectors:
                should_queries.append(
                    ESQ("terms", **{"sectors.raw": sectors, "boost": 2.0})
                )

            # Add metadata similarity
            # Dataset.metadata is the related_name for DatasetMetadata
            from api.models import DatasetMetadata

            dataset_metadata_items = dataset.metadata.all().select_related("metadata_item")  # type: ignore
            if dataset_metadata_items:
                for item in dataset_metadata_items:
                    # Explicitly cast to DatasetMetadata
                    metadata_item = cast(DatasetMetadata, item)
                    if metadata_item.value and metadata_item.metadata_item:
                        # Add nested query for metadata
                        should_queries.append(
                            ESQ(
                                "nested",
                                path="metadata",
                                query=ESQ(
                                    "bool",
                                    must=[
                                        ESQ(
                                            "match",
                                            **{
                                                "metadata.metadata_item.label": metadata_item.metadata_item.label
                                            },
                                        ),
                                        ESQ(
                                            "match",
                                            **{"metadata.value": metadata_item.value},
                                        ),
                                    ],
                                ),
                                boost=1.5,
                            )
                        )

            # Combine all similarity criteria
            query = ESQ("bool", should=should_queries, minimum_should_match=1)

            # Exclude the current dataset
            exclude_query = ESQ("bool", must_not=[ESQ("term", id=dataset.id)])
            final_query = ESQ("bool", must=[query, exclude_query])

            # Execute the search
            search = search.query(final_query)

            # Limit to 5 similar datasets
            search = search[:5]

            # Execute the search
            response = search.execute()

            # Get the dataset IDs from the search results
            dataset_ids = [hit.id for hit in response]

            # Fetch the actual dataset objects
            if dataset_ids:
                # Get Django Dataset objects
                django_datasets = Dataset.objects.filter(id__in=dataset_ids)
                # Convert to TypeDataset objects
                return TypeDataset.from_django_list(django_datasets)  # type: ignore

            return []
        except Exception as e:
            logger.error(f"Error fetching similar datasets: {str(e)}")
            return []

    @strawberry.field
    def is_individual_dataset(self) -> bool:
        """Check if this dataset is published by a individual publisher instead of organization."""
        return self.organization is None


@strawberry_django.type(Tag, fields="__all__")
class TypeTag(BaseType):
    """Type for tag."""

    id: strawberry.auto
    value: strawberry.auto
