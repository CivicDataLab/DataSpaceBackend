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

        return super().get("/api/search/aimodel/", params=params)

    def get_by_id(self, model_id: str) -> Dict[str, Any]:
        """
        Get an AI model by ID.

        Args:
            model_id: UUID of the AI model

        Returns:
            Dictionary containing AI model information
        """
        # Use parent class get method with full endpoint path
        return super().get(f"/api/aimodels/{model_id}/")

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
                versions {
                    id
                    version
                    versionNotes
                    lifecycleStage
                    isLatest
                    supportsStreaming
                    maxTokens
                    supportedLanguages
                    inputSchema
                    outputSchema
                    status
                    createdAt
                    updatedAt
                    publishedAt
                    providers {
                        id
                        provider
                        providerModelId
                        isPrimary
                        isActive
                        hfUsePipeline
                        hfAuthToken
                        hfModelClass
                        hfAttnImplementation
                        framework
                        config
                    }
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
    ) -> Any:
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
                versions {
                    id
                    version
                    lifecycleStage
                    isLatest
                    status
                    providers {
                        id
                        provider
                        providerModelId
                        isPrimary
                    }
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
        models_result: Any = data.get("aiModels", []) if isinstance(data, dict) else []
        return models_result

    def get_organization_models(
        self,
        organization_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
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

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new AI model.

        Args:
            data: Dictionary containing AI model data

        Returns:
            Dictionary containing created AI model information
        """
        return self.post("/api/aimodels/", json_data=data)

    def update(self, model_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing AI model.

        Args:
            model_id: UUID of the AI model
            data: Dictionary containing updated AI model data

        Returns:
            Dictionary containing updated AI model information
        """
        return self.patch(f"/api/aimodels/{model_id}/", json_data=data)

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        """
        Delete an AI model.

        Args:
            model_id: UUID of the AI model

        Returns:
            Dictionary containing deletion response
        """
        return self.delete(f"/api/aimodels/{model_id}/")

    def call_model(
        self, model_id: str, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call an AI model with input text using the appropriate client (API or HuggingFace).

        Args:
            model_id: UUID of the AI model
            input_text: Input text to process
            parameters: Optional parameters for the model call (temperature, max_tokens, etc.)

        Returns:
            Dictionary containing model response:
            {
                "success": bool,
                "output": str (if successful),
                "error": str (if failed),
                "latency_ms": float,
                "provider": str,
                ...
            }
        """
        return self.post(
            f"/api/aimodels/{model_id}/call/",
            json_data={"input_text": input_text, "parameters": parameters or {}},
        )

    def call_model_async(
        self, model_id: str, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call an AI model asynchronously (returns task ID for long-running operations).

        Args:
            model_id: UUID of the AI model
            input_text: Input text to process
            parameters: Optional parameters for the model call

        Returns:
            Dictionary containing task information:
            {
                "task_id": str,
                "status": str,
                "model_id": str
            }
        """
        return self.post(
            f"/api/aimodels/{model_id}/call-async/",
            json_data={"input_text": input_text, "parameters": parameters or {}},
        )

    # ==================== Version Management ====================

    def get_versions(self, model_id: int) -> List[Dict[str, Any]]:
        """
        Get all versions for an AI model.

        Args:
            model_id: ID of the AI model

        Returns:
            List of version dictionaries
        """
        query = """
        query GetModelVersions($filters: AIModelFilter) {
            aiModels(filters: $filters) {
                versions {
                    id
                    version
                    versionNotes
                    lifecycleStage
                    isLatest
                    supportsStreaming
                    maxTokens
                    supportedLanguages
                    status
                    createdAt
                    updatedAt
                    publishedAt
                    providers {
                        id
                        provider
                        providerModelId
                        isPrimary
                        isActive
                    }
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"filters": {"id": model_id}},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        models = response.get("data", {}).get("aiModels", [])
        if models:
            result: List[Dict[str, Any]] = models[0].get("versions", [])
            return result
        return []

    def create_version(
        self,
        model_id: int,
        version: str,
        lifecycle_stage: str = "DEVELOPMENT",
        is_latest: bool = False,
        copy_from_version_id: Optional[int] = None,
        version_notes: Optional[str] = None,
        supports_streaming: bool = False,
        max_tokens: Optional[int] = None,
        supported_languages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new version for an AI model.

        Args:
            model_id: ID of the AI model
            version: Version string (e.g., "1.0", "2.1")
            lifecycle_stage: One of DEVELOPMENT, TESTING, BETA, STAGING, PRODUCTION, DEPRECATED, RETIRED
            is_latest: Whether this should be the primary version
            copy_from_version_id: Optional version ID to copy providers from
            version_notes: Optional notes about this version
            supports_streaming: Whether this version supports streaming
            max_tokens: Maximum tokens supported
            supported_languages: List of supported language codes

        Returns:
            Dictionary containing created version information
        """
        mutation = """
        mutation CreateAIModelVersion($input: CreateAIModelVersionInput!) {
            createAiModelVersion(input: $input) {
                success
                data {
                    id
                    version
                    lifecycleStage
                    isLatest
                    status
                }
                errors
            }
        }
        """

        input_data: Dict[str, Any] = {
            "modelId": model_id,
            "version": version,
            "lifecycleStage": lifecycle_stage,
            "isLatest": is_latest,
            "supportsStreaming": supports_streaming,
        }

        if copy_from_version_id:
            input_data["copyFromVersionId"] = copy_from_version_id
        if version_notes:
            input_data["versionNotes"] = version_notes
        if max_tokens:
            input_data["maxTokens"] = max_tokens
        if supported_languages:
            input_data["supportedLanguages"] = supported_languages

        response = self.post(
            "/api/graphql",
            json_data={
                "query": mutation,
                "variables": {"input": input_data},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("createAiModelVersion", {})
        return result

    def update_version(
        self,
        version_id: int,
        version: Optional[str] = None,
        lifecycle_stage: Optional[str] = None,
        is_latest: Optional[bool] = None,
        version_notes: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an AI model version.

        Args:
            version_id: ID of the version to update
            version: New version string
            lifecycle_stage: New lifecycle stage
            is_latest: Whether this should be the primary version
            version_notes: New version notes
            status: New status

        Returns:
            Dictionary containing updated version information
        """
        mutation = """
        mutation UpdateAIModelVersion($input: UpdateAIModelVersionInput!) {
            updateAiModelVersion(input: $input) {
                success
                data {
                    id
                    version
                    lifecycleStage
                    isLatest
                    status
                }
                errors
            }
        }
        """

        input_data: Dict[str, Any] = {"id": version_id}

        if version is not None:
            input_data["version"] = version
        if lifecycle_stage is not None:
            input_data["lifecycleStage"] = lifecycle_stage
        if is_latest is not None:
            input_data["isLatest"] = is_latest
        if version_notes is not None:
            input_data["versionNotes"] = version_notes
        if status is not None:
            input_data["status"] = status

        response = self.post(
            "/api/graphql",
            json_data={
                "query": mutation,
                "variables": {"input": input_data},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("updateAiModelVersion", {})
        return result

    # ==================== Provider Management ====================

    def get_version_providers(self, version_id: int) -> List[Dict[str, Any]]:
        """
        Get all providers for a specific version.

        Args:
            version_id: ID of the version

        Returns:
            List of provider dictionaries
        """
        query = """
        query GetVersionProviders($versionId: Int!) {
            aiModelVersion(id: $versionId) {
                providers {
                    id
                    provider
                    providerModelId
                    isPrimary
                    isActive
                    hfUsePipeline
                    hfAuthToken
                    hfModelClass
                    hfAttnImplementation
                    framework
                    config
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"versionId": version_id},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        version_data = response.get("data", {}).get("aiModelVersion", {})
        result: List[Dict[str, Any]] = version_data.get("providers", []) if version_data else []
        return result

    def create_provider(
        self,
        version_id: int,
        provider: str,
        provider_model_id: str,
        is_primary: bool = False,
        hf_use_pipeline: bool = False,
        hf_model_class: Optional[str] = None,
        hf_auth_token: Optional[str] = None,
        hf_attn_implementation: Optional[str] = None,
        framework: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new provider for a version.

        Args:
            version_id: ID of the version
            provider: Provider type (OPENAI, LLAMA_OLLAMA, LLAMA_TOGETHER, LLAMA_REPLICATE,
                     LLAMA_CUSTOM, CUSTOM, HUGGINGFACE)
            provider_model_id: Model ID at the provider (e.g., "gpt-4", "meta-llama/Llama-2-7b")
            is_primary: Whether this is the primary provider
            hf_use_pipeline: For HuggingFace - whether to use pipeline API
            hf_model_class: For HuggingFace - model class (e.g., "AutoModelForCausalLM")
            hf_auth_token: For HuggingFace - auth token for gated models
            hf_attn_implementation: For HuggingFace - attention implementation
            framework: Framework (pt, tf)
            config: Additional configuration (apiKey, baseUrl, authType, etc.)

        Returns:
            Dictionary containing created provider information
        """
        mutation = """
        mutation CreateVersionProvider($input: CreateVersionProviderInput!) {
            createVersionProvider(input: $input) {
                success
                data {
                    id
                    provider
                    providerModelId
                    isPrimary
                    isActive
                }
                errors
            }
        }
        """

        input_data: Dict[str, Any] = {
            "versionId": version_id,
            "provider": provider,
            "providerModelId": provider_model_id,
            "isPrimary": is_primary,
            "hfUsePipeline": hf_use_pipeline,
        }

        if hf_model_class:
            input_data["hfModelClass"] = hf_model_class
        if hf_auth_token:
            input_data["hfAuthToken"] = hf_auth_token
        if hf_attn_implementation:
            input_data["hfAttnImplementation"] = hf_attn_implementation
        if framework:
            input_data["framework"] = framework
        if config:
            input_data["config"] = config

        response = self.post(
            "/api/graphql",
            json_data={
                "query": mutation,
                "variables": {"input": input_data},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("createVersionProvider", {})
        return result

    def update_provider(
        self,
        provider_id: int,
        provider_model_id: Optional[str] = None,
        is_primary: Optional[bool] = None,
        hf_use_pipeline: Optional[bool] = None,
        hf_model_class: Optional[str] = None,
        hf_auth_token: Optional[str] = None,
        hf_attn_implementation: Optional[str] = None,
        framework: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update a provider.

        Args:
            provider_id: ID of the provider to update
            provider_model_id: New model ID at the provider
            is_primary: Whether this is the primary provider
            hf_use_pipeline: For HuggingFace - whether to use pipeline API
            hf_model_class: For HuggingFace - model class
            hf_auth_token: For HuggingFace - auth token
            hf_attn_implementation: For HuggingFace - attention implementation
            framework: Framework (pt, tf)
            config: Additional configuration

        Returns:
            Dictionary containing updated provider information
        """
        mutation = """
        mutation UpdateVersionProvider($input: UpdateVersionProviderInput!) {
            updateVersionProvider(input: $input) {
                success
                data {
                    id
                    provider
                    providerModelId
                    isPrimary
                    isActive
                }
                errors
            }
        }
        """

        input_data: Dict[str, Any] = {"id": provider_id}

        if provider_model_id is not None:
            input_data["providerModelId"] = provider_model_id
        if is_primary is not None:
            input_data["isPrimary"] = is_primary
        if hf_use_pipeline is not None:
            input_data["hfUsePipeline"] = hf_use_pipeline
        if hf_model_class is not None:
            input_data["hfModelClass"] = hf_model_class
        if hf_auth_token is not None:
            input_data["hfAuthToken"] = hf_auth_token
        if hf_attn_implementation is not None:
            input_data["hfAttnImplementation"] = hf_attn_implementation
        if framework is not None:
            input_data["framework"] = framework
        if config is not None:
            input_data["config"] = config

        response = self.post(
            "/api/graphql",
            json_data={
                "query": mutation,
                "variables": {"input": input_data},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("updateVersionProvider", {})
        return result

    def delete_provider(self, provider_id: int) -> Dict[str, Any]:
        """
        Delete a provider.

        Args:
            provider_id: ID of the provider to delete

        Returns:
            Dictionary containing deletion response
        """
        mutation = """
        mutation DeleteVersionProvider($providerId: Int!) {
            deleteVersionProvider(providerId: $providerId) {
                success
                errors
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": mutation,
                "variables": {"providerId": provider_id},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("deleteVersionProvider", {})
        return result

    # ==================== Helper Methods ====================

    def get_primary_version(self, model_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the primary (latest) version for an AI model.

        Args:
            model_id: ID of the AI model

        Returns:
            Dictionary containing the primary version, or None if no versions exist
        """
        versions = self.get_versions(model_id)
        for version in versions:
            if version.get("isLatest"):
                return version
        return versions[0] if versions else None

    def get_primary_provider(self, version_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the primary provider for a version.

        Args:
            version_id: ID of the version

        Returns:
            Dictionary containing the primary provider, or None if no providers exist
        """
        providers = self.get_version_providers(version_id)
        for provider in providers:
            if provider.get("isPrimary"):
                return provider
        return providers[0] if providers else None
