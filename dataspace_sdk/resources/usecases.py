"""UseCase resource client for DataSpace SDK."""

from typing import Any, Dict, List, Optional

from dataspace_sdk.base import BaseAPIClient


class UseCaseClient(BaseAPIClient):
    """Client for interacting with UseCase resources."""

    def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        geographies: Optional[List[str]] = None,
        status: Optional[str] = None,
        running_status: Optional[str] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for use cases using Elasticsearch.

        Args:
            query: Search query string
            tags: Filter by tags
            sectors: Filter by sectors
            geographies: Filter by geographies
            status: Filter by status (DRAFT, PUBLISHED, etc.)
            running_status: Filter by running status (INITIATED, ONGOING, COMPLETED)
            sort: Sort order (recent, alphabetical, started_on, completed_on)
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
        if running_status:
            params["running_status"] = running_status
        if sort:
            params["sort"] = sort

        return super().get("/api/search/usecase/", params=params)

    def get_by_id(self, usecase_id: int) -> Dict[str, Any]:
        """
        Get a use case by ID using GraphQL.

        Args:
            usecase_id: ID of the use case

        Returns:
            Dictionary containing use case information
        """
        query = """
        query GetUseCase($id: ID!) {
            useCase(id: $id) {
                id
                title
                summary
                status
                runningStatus
                platformUrl
                logo
                startedOn
                completedOn
                createdAt
                updatedAt
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
                sdgs {
                    id
                    name
                    description
                }
                datasets {
                    id
                    title
                    description
                }
                organizations {
                    id
                    organization {
                        id
                        name
                    }
                    relationshipType
                }
                contributors {
                    id
                    username
                    firstName
                    lastName
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"id": str(usecase_id)},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("useCase", {})
        return result

    def list_all(
        self,
        status: Optional[str] = None,
        running_status: Optional[str] = None,
        organization_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        """
        List all use cases with pagination using GraphQL.

        Args:
            status: Filter by status
            running_status: Filter by running status
            organization_id: Filter by organization
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing list of use cases
        """
        query = """
        query ListUseCases($filters: UseCaseFilter, $pagination: OffsetPaginationInput) {
            useCases(filters: $filters, pagination: $pagination) {
                id
                title
                summary
                status
                runningStatus
                platformUrl
                startedOn
                completedOn
                createdAt
                updatedAt
                tags {
                    id
                    value
                }
                sectors {
                    id
                    name
                }
                organizations {
                    id
                    organization {
                        id
                        name
                    }
                    relationshipType
                }
            }
        }
        """

        filters: Dict[str, Any] = {}
        if status:
            filters["status"] = status
        if running_status:
            filters["runningStatus"] = running_status
        if organization_id:
            filters["organizations"] = {"organization": {"id": {"exact": organization_id}}}

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
        usecases_result: Any = data.get("useCases", []) if isinstance(data, dict) else []
        return usecases_result

    def get_organization_usecases(
        self,
        organization_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        """
        Get use cases for a specific organization.

        Args:
            organization_id: UUID of the organization
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing organization's use cases
        """
        return self.list_all(
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
