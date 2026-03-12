"""Sector resource client for DataSpace SDK."""

from typing import Any, Dict, List, Optional

from dataspace_sdk.base import BaseAPIClient


class SectorClient(BaseAPIClient):
    """Client for interacting with Sector resources."""

    def list_all(
        self,
        search: Optional[str] = None,
        min_dataset_count: Optional[int] = None,
        min_aimodel_count: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List all sectors with optional filters using GraphQL.

        Args:
            search: Search query for name/description
            min_dataset_count: Filter sectors with at least this many published datasets
            min_aimodel_count: Filter sectors with at least this many active AI models
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            List of sector dictionaries
        """
        query = """
        query ListSectors($filters: SectorFilter, $pagination: OffsetPaginationInput) {
            sectors(filters: $filters, pagination: $pagination) {
                id
                name
                slug
                description
                datasetCount
                aimodelCount
            }
        }
        """

        filters: Dict[str, Any] = {}
        if search:
            filters["search"] = search
        if min_dataset_count is not None:
            filters["minDatasetCount"] = min_dataset_count
        if min_aimodel_count is not None:
            filters["minAimodelCount"] = min_aimodel_count

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
        sectors_result: List[Dict[str, Any]] = (
            data.get("sectors", []) if isinstance(data, dict) else []
        )
        return sectors_result

    def get_by_id(self, sector_id: str) -> Dict[str, Any]:
        """
        Get a sector by ID using GraphQL.

        Args:
            sector_id: UUID of the sector

        Returns:
            Dictionary containing sector information
        """
        query = """
        query GetSector($id: UUID!) {
            sector(id: $id) {
                id
                name
                slug
                description
                datasetCount
                aimodelCount
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"id": sector_id},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("sector", {})
        return result

    def get_sectors_with_aimodels(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get sectors that have at least one active AI model.

        Args:
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            List of sector dictionaries with AI models
        """
        return self.list_all(min_aimodel_count=1, limit=limit, offset=offset)
