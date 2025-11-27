"""Dataset resource client for DataSpace SDK."""

from typing import Any, Dict, List, Optional

from dataspace_sdk.base import BaseAPIClient


class DatasetClient(BaseAPIClient):
    """Client for interacting with Dataset resources."""

    def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        geographies: Optional[List[str]] = None,
        status: Optional[str] = None,
        access_type: Optional[str] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for datasets using Elasticsearch.

        Args:
            query: Search query string
            tags: Filter by tags
            sectors: Filter by sectors
            geographies: Filter by geographies
            status: Filter by status (DRAFT, PUBLISHED, etc.)
            access_type: Filter by access type (OPEN, RESTRICTED, etc.)
            sort: Sort order (recent, alphabetical)
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Dictionary containing search results and metadata
        """
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }

        if query:
            params["q"] = query
        if tags:
            params["tags"] = ",".join(tags)
        if sectors:
            params["sectors"] = ",".join(sectors)
        if geographies:
            params["geographies"] = ",".join(geographies)
        if status:
            params["status"] = status
        if access_type:
            params["access_type"] = access_type
        if sort:
            params["sort"] = sort

        return super().get("/api/search/dataset/", params=params)

    def get_by_id(self, dataset_id: str) -> Dict[str, Any]:
        """
        Get a dataset by ID using GraphQL.

        Args:
            dataset_id: UUID of the dataset

        Returns:
            Dictionary containing dataset information
        """
        query = """
        query GetDataset($id: UUID!) {
            dataset(id: $id) {
                id
                title
                description
                status
                accessType
                license
                createdAt
                updatedAt
                organization {
                    id
                    name
                    description
                }
                tags {
                    id
                    value
                }
                sectors {
                    id
                    name
                }
                geographies {
                    id
                    name
                }
                resources {
                    id
                    title
                    description
                    fileDetails
                    schema
                    createdAt
                    updatedAt
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"id": dataset_id},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("dataset", {})
        return result

    def list_all(
        self,
        status: Optional[str] = None,
        organization_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        """
        List all datasets with pagination using GraphQL.

        Args:
            status: Filter by status
            organization_id: Filter by organization
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing list of datasets
        """
        query = """
        query ListDatasets($filters: DatasetFilter, $pagination: OffsetPaginationInput) {
            datasets(filters: $filters, pagination: $pagination) {
                id
                title
                description
                status
                accessType
                license
                createdAt
                updatedAt
                organization {
                    id
                    name
                }
                tags {
                    id
                    value
                }
            }
        }
        """

        filters: Dict[str, Any] = {}
        if status:
            filters["status"] = status
        if organization_id:
            filters["organization"] = {"id": {"exact": organization_id}}

        variables: Dict[str, Any] = {
            "pagination": {"limit": limit, "offset": offset},
        }
        if filters:
            variables["filters"] = filters

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": variables,
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        data = response.get("data", {})
        datasets_result: Any = data.get("datasets", []) if isinstance(data, dict) else []
        return datasets_result

    def get_trending(self, limit: int = 10) -> Dict[str, Any]:
        """
        Get trending datasets.

        Args:
            limit: Number of results to return

        Returns:
            Dictionary containing trending datasets
        """
        return self.get("/api/trending/datasets/", params={"limit": limit})

    def get_organization_datasets(
        self,
        organization_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        """
        Get datasets for a specific organization.

        Args:
            organization_id: UUID of the organization
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing organization's datasets
        """
        return self.list_all(
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
