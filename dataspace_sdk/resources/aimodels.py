"""AI Model resource client for DataSpace SDK."""

from typing import Any, Dict, List, Optional

from dataspace_sdk.base import BaseAPIClient


class AIModelClient(BaseAPIClient):
    """Client for interacting with AI Model resources."""

    def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        geographies: Optional[List[str]] = None,
        status: Optional[str] = None,
        model_type: Optional[str] = None,
        provider: Optional[str] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for AI models using Elasticsearch.

        Args:
            query: Search query string
            tags: Filter by tags
            sectors: Filter by sectors
            geographies: Filter by geographies
            status: Filter by status (ACTIVE, INACTIVE, etc.)
            model_type: Filter by model type (LLM, VISION, etc.)
            provider: Filter by provider (OPENAI, ANTHROPIC, etc.)
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
        if model_type:
            params["model_type"] = model_type
        if provider:
            params["provider"] = provider
        if sort:
            params["sort"] = sort

        return self.get("/api/search/aimodel/", params=params)

    def get_by_id(self, model_id: str) -> Dict[str, Any]:
        """
        Get an AI model by ID.

        Args:
            model_id: UUID of the AI model

        Returns:
            Dictionary containing AI model information
        """
        return self.get(f"/api/aimodels/{model_id}/")

    def get_by_id_graphql(self, model_id: str) -> Dict[str, Any]:
        """
        Get an AI model by ID using GraphQL.

        Args:
            model_id: UUID of the AI model

        Returns:
            Dictionary containing AI model information
        """
        query = """
        query GetAIModel($id: UUID!) {
            aiModel(id: $id) {
                id
                name
                displayName
                description
                modelType
                provider
                version
                providerModelId
                supportsStreaming
                maxTokens
                supportedLanguages
                inputSchema
                outputSchema
                status
                isPublic
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
                sectors {
                    id
                    name
                }
                geographies {
                    id
                    name
                }
                endpoints {
                    id
                    name
                    url
                    httpMethod
                    authType
                    isActive
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"id": model_id},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("aiModel", {})
        return result

    def list_all(
        self,
        status: Optional[str] = None,
        organization_id: Optional[str] = None,
        model_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List all AI models with pagination using GraphQL.

        Args:
            status: Filter by status
            organization_id: Filter by organization
            model_type: Filter by model type
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing list of AI models
        """
        query = """
        query ListAIModels($filters: AIModelFilter, $pagination: OffsetPaginationInput) {
            aiModels(filters: $filters, pagination: $pagination) {
                id
                name
                displayName
                description
                modelType
                provider
                version
                status
                isPublic
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
        if model_type:
            filters["modelType"] = model_type

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
        models_result: Dict[str, Any] = data.get("aiModels", []) if isinstance(data, dict) else []
        return models_result

    def get_organization_models(
        self,
        organization_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get AI models for a specific organization.

        Args:
            organization_id: UUID of the organization
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            Dictionary containing organization's AI models
        """
        return self.list_all(
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
