"""Publication ("Resource") resource client for DataSpace SDK."""

from typing import Any, Dict, List, Optional

from dataspace_sdk.base import BaseAPIClient


class PublicationClient(BaseAPIClient):
    """Client for interacting with Resources (internally 'publications').

    Search runs over the REST Elasticsearch endpoint; detail/list/CRUD go
    through GraphQL, matching the backend (Resources have no REST write API).
    """

    def search(
        self,
        query: Optional[str] = None,
        resource_type: Optional[str] = None,
        sectors: Optional[List[str]] = None,
        geographies: Optional[List[str]] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """Search published resources via Elasticsearch.

        Args:
            query: Free-text query.
            resource_type: Filter by resource type name.
            sectors: Filter by sector names.
            geographies: Filter by geography names.
            sort: Sort order (recent, alphabetical, created).
            page: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            Search results and metadata.
        """
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if query:
            params["q"] = query
        if resource_type:
            params["resource_type"] = resource_type
        if sectors:
            params["sectors"] = ",".join(sectors)
        if geographies:
            params["geographies"] = ",".join(geographies)
        if sort:
            params["sort"] = sort

        return super().get("/api/search/publication/", params=params)

    def get_by_id(self, publication_id: str) -> Dict[str, Any]:
        """Get a single resource by id via GraphQL."""
        query = """
        query GetPublication($publicationId: UUID!) {
            getPublication(publicationId: $publicationId) {
                id title description slug status authors publicationDate
                license externalSourceLink downloadCount
                resourceType { id name }
                blocks { id position blockType fileName youtubeUrl }
            }
        }
        """
        return self.post(
            "/api/graphql",
            json_data={"query": query, "variables": {"publicationId": publication_id}},
        )

    def list_all(
        self,
        include_public: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List resources scoped to the caller (org header or user) via GraphQL."""
        query = """
        query ListPublications($includePublic: Boolean, $pagination: OffsetPaginationInput) {
            publications(includePublic: $includePublic, pagination: $pagination) {
                id title slug status
            }
        }
        """
        variables: Dict[str, Any] = {
            "includePublic": include_public,
            "pagination": {"offset": offset, "limit": limit},
        }
        return self.post("/api/graphql", json_data={"query": query, "variables": variables})

    def get_organization_publications(self, limit: int = 10, offset: int = 0) -> Dict[str, Any]:
        """List the current organization's resources (org set via set_organization)."""
        return self.list_all(include_public=False, limit=limit, offset=offset)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a resource via the createPublication mutation."""
        mutation = """
        mutation CreatePublication($input: CreatePublicationInput!) {
            createPublication(input: $input) {
                success errors { nonFieldErrors } data { id slug status }
            }
        }
        """
        return self.post(
            "/api/graphql", json_data={"query": mutation, "variables": {"input": data}}
        )

    def update(self, publication_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a resource via the updatePublication mutation."""
        mutation = """
        mutation UpdatePublication($input: UpdatePublicationInput!) {
            updatePublication(input: $input) {
                success errors { nonFieldErrors } data { id title }
            }
        }
        """
        payload = {"id": publication_id, **data}
        return self.post(
            "/api/graphql",
            json_data={"query": mutation, "variables": {"input": payload}},
        )

    def delete(self, publication_id: str) -> Dict[str, Any]:
        """Delete a resource via the deletePublication mutation."""
        mutation = """
        mutation DeletePublication($publicationId: UUID!) {
            deletePublication(publicationId: $publicationId) { success data }
        }
        """
        return self.post(
            "/api/graphql",
            json_data={"query": mutation, "variables": {"publicationId": publication_id}},
        )
