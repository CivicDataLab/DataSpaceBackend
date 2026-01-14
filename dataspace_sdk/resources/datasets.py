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
        dataset_type: Optional[str] = None,
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
            dataset_type: Filter by dataset type (DATA, PROMPT)
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
        if dataset_type:
            params["dataset_type"] = dataset_type
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
                created
                updated
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
                    name
                    description
                    fileDetails {
                        format
                        size
                    }
                    schema
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
                created
                updated
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

    def create(self, dataset_type: str = "DATA") -> Dict[str, Any]:
        """
        Create a new dataset using GraphQL.

        Args:
            dataset_type: Type of dataset to create (DATA or PROMPT)

        Returns:
            Dictionary containing the created dataset information
        """
        query = """
        mutation AddDataset($createInput: CreateDatasetInput) {
            addDataset(createInput: $createInput) {
                success
                errors
                data {
                    id
                    title
                    description
                    status
                    datasetType
                    created
                    updated
                }
            }
        }
        """

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"createInput": {"datasetType": dataset_type}},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("addDataset", {})
        return result

    def get_prompt_by_id(self, dataset_id: str) -> Dict[str, Any]:
        """
        Get a prompt dataset by ID with prompt-specific metadata.

        Args:
            dataset_id: UUID of the prompt dataset

        Returns:
            Dictionary containing prompt dataset information including prompt metadata
        """
        query = """
        query GetPromptDataset($id: UUID!) {
            dataset(id: $id) {
                id
                title
                description
                status
                accessType
                license
                datasetType
                created
                updated
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
                    name
                    fileDetails {
                        format
                        size
                    }
                    promptDetails {
                        promptFormat
                        hasSystemPrompt
                        hasExampleResponses
                        promptCount
                    }
                }
                promptMetadata
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

    def list_prompts(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        domain: Optional[str] = None,
        organization_id: Optional[str] = None,
        include_public: Optional[bool] = False,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        """
        List prompt datasets with pagination using GraphQL.

        Args:
            status: Filter by status (DRAFT, PUBLISHED, etc.)
            task_type: Filter by prompt task type
            domain: Filter by domain
            organization_id: Filter by organization
            include_public: Include public datasets
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            List of prompt datasets
        """
        query = """
        query ListPromptDatasets($filters: DatasetFilter, $pagination: OffsetPaginationInput, $include_public: Boolean) {
            datasets(filters: $filters, pagination: $pagination, includePublic: $include_public) {
                id
                title
                description
                status
                accessType
                datasetType
                created
                organization {
                    id
                    name
                }
                tags {
                    id
                    value
                }
                promptMetadata
                resources {
                    id
                    name
                    fileDetails {
                        format
                        size
                    }
                    promptDetails {
                        promptFormat
                        hasSystemPrompt
                        hasExampleResponses
                        promptCount
                    }
                }
            }
        }
        """

        filters: Dict[str, Any] = {"datasetType": "PROMPT"}
        if status:
            filters["status"] = status
        if organization_id:
            filters["organization"] = {"id": {"exact": organization_id}}

        variables: Dict[str, Any] = {
            "pagination": {"limit": limit, "offset": offset},
            "filters": filters,
            "include_public": include_public,
        }

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

    def search_prompts(
        self,
        query: Optional[str] = None,
        task_type: Optional[str] = None,
        domain: Optional[str] = None,
        target_languages: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for prompt datasets specifically.

        Args:
            query: Search query string
            task_type: Filter by prompt task type (TEXT_GENERATION, QUESTION_ANSWERING, etc.)
            domain: Filter by domain (healthcare, education, etc.)
            target_languages: Filter by target languages
            tags: Filter by tags
            sectors: Filter by sectors
            sort: Sort order (recent, alphabetical)
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Dictionary containing search results and metadata
        """
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "dataset_type": "PROMPT",
        }

        if query:
            params["q"] = query
        if task_type:
            params["task_type"] = task_type
        if domain:
            params["domain"] = domain
        if target_languages:
            params["target_languages"] = ",".join(target_languages)
        if tags:
            params["tags"] = ",".join(tags)
        if sectors:
            params["sectors"] = ",".join(sectors)
        if sort:
            params["sort"] = sort

        return super().get("/api/search/dataset/", params=params)

    def update_prompt_metadata(
        self,
        dataset_id: str,
        task_type: Optional[str] = None,
        target_languages: Optional[List[str]] = None,
        domain: Optional[str] = None,
        target_model_types: Optional[List[str]] = None,
        prompt_format: Optional[str] = None,
        has_system_prompt: Optional[bool] = None,
        has_example_responses: Optional[bool] = None,
        avg_prompt_length: Optional[int] = None,
        prompt_count: Optional[int] = None,
        use_case: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update prompt-specific metadata for a prompt dataset.

        Args:
            dataset_id: UUID of the prompt dataset
            task_type: Type of prompt task
            target_languages: List of target languages
            domain: Domain/category of prompts
            target_model_types: List of target AI model types
            prompt_format: Format of prompts
            has_system_prompt: Whether prompts include system instructions
            has_example_responses: Whether prompts include example responses
            avg_prompt_length: Average prompt length
            prompt_count: Total number of prompts
            use_case: Description of intended use cases

        Returns:
            Dictionary containing the updated prompt metadata
        """
        query = """
        mutation UpdatePromptMetadata($updateInput: UpdatePromptMetadataInput!) {
            updatePromptMetadata(updateInput: $updateInput) {
                success
                errors
                data {
                    id
                    title
                    description
                    status
                    datasetType
                    taskType
                    targetLanguages
                    domain
                    targetModelTypes
                    promptFormat
                    hasSystemPrompt
                    hasExampleResponses
                    avgPromptLength
                    promptCount
                    useCase
                }
            }
        }
        """

        variables: Dict[str, Any] = {"dataset": dataset_id}

        if task_type is not None:
            variables["taskType"] = task_type
        if target_languages is not None:
            variables["targetLanguages"] = target_languages
        if domain is not None:
            variables["domain"] = domain
        if target_model_types is not None:
            variables["targetModelTypes"] = target_model_types
        if prompt_format is not None:
            variables["promptFormat"] = prompt_format
        if has_system_prompt is not None:
            variables["hasSystemPrompt"] = has_system_prompt
        if has_example_responses is not None:
            variables["hasExampleResponses"] = has_example_responses
        if avg_prompt_length is not None:
            variables["avgPromptLength"] = avg_prompt_length
        if prompt_count is not None:
            variables["promptCount"] = prompt_count
        if use_case is not None:
            variables["useCase"] = use_case

        response = self.post(
            "/api/graphql",
            json_data={
                "query": query,
                "variables": {"updateInput": variables},
            },
        )

        if "errors" in response:
            from dataspace_sdk.exceptions import DataSpaceAPIError

            raise DataSpaceAPIError(f"GraphQL error: {response['errors']}")

        result: Dict[str, Any] = response.get("data", {}).get("updatePromptMetadata", {})
        return result
