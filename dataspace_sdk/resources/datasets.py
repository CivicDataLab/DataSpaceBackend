"""Dataset resource client for DataSpace SDK."""

from typing import Any, Dict, Iterator, List, Optional

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
            getDataset(datasetId: $id) {
                id
                title
                description
                status
                datasetType
                created
                modified
                downloadCount
                organization {
                    id
                    name
                    description
                }
                user {
                    id
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
                    schema {
                        id
                        fieldName
                        format
                        description
                    }
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

        result: Dict[str, Any] = response.get("data", {}).get("getDataset", {})
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
                datasetType
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
            getDataset(datasetId: $id) {
                id
                title
                description
                status
                datasetType
                created
                modified
                downloadCount
                organization {
                    id
                    name
                    description
                }
                user {
                    id
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

        result: Dict[str, Any] = response.get("data", {}).get("getDataset", {})
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

    # ------------------------------------------------------------------
    # Indexed data access (data_db)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_data_params(
        filters: Optional[Dict[str, Any]],
        columns: Optional[List[str]],
        order_by: Optional[List[str]],
        limit: int,
        offset: int,
        count: Optional[bool],
    ) -> Dict[str, Any]:
        """Translate Pythonic kwargs into the ``GET /data/`` query-string form.

        ``filters`` is a flat dict using the same ``col`` / ``col__op`` keys as
        the server. List values are passed through (requests will emit one
        ``key=v`` pair per entry, used by ``__in`` / ``__nin``).
        """
        params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if columns:
            params["columns"] = ",".join(columns)
        if order_by:
            params["order_by"] = ",".join(order_by)
        if count is not None:
            params["count"] = "true" if count else "false"
        if filters:
            for k, v in filters.items():
                if isinstance(v, (list, tuple)):
                    params[k] = list(v)
                elif isinstance(v, bool):
                    params[k] = "true" if v else "false"
                else:
                    params[k] = v
        return params

    def get_resource_data(
        self,
        resource_id: str,
        filters: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        count: bool = True,
    ) -> Dict[str, Any]:
        """Fetch indexed (saved in ``data_db``) data for a single resource.

        Args:
            resource_id: UUID of the resource (must have an indexed table).
            filters: Column-level filters. Keys are either ``"col"`` (equality)
                or ``"col__op"`` where op is one of: ``eq, ne, gt, gte, lt,
                lte, in, nin, contains, icontains, startswith, istartswith,
                endswith, iendswith, isnull, notnull``.
            columns: Subset of columns to project. ``None`` returns all.
            order_by: Columns to sort by. Prefix with ``-`` for DESC.
            limit: Max rows to return (server caps at 10000).
            offset: Number of rows to skip.
            count: If ``True``, the response includes total matching row count.

        Returns:
            A dict with ``columns``, ``rows``, ``total``, ``limit``,
            ``offset``, ``available_columns``, ``resource_id``,
            ``dataset_id``, and ``max_limit``.
        """
        params = self._build_data_params(filters, columns, order_by, limit, offset, count)
        return self.get(f"/api/resources/{resource_id}/data/", params=params)

    def get_dataset_data(
        self,
        dataset_id: str,
        resource_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        count: bool = True,
    ) -> Dict[str, Any]:
        """Fetch indexed data for a dataset.

        By default operates on the dataset's first indexed (tabular) resource.
        Pass ``resource_id`` to target a specific resource within the dataset.
        Filtering / column / ordering semantics are identical to
        :meth:`get_resource_data`.
        """
        params = self._build_data_params(filters, columns, order_by, limit, offset, count)
        if resource_id:
            params["resource_id"] = resource_id
        return self.get(f"/api/datasets/{dataset_id}/data/", params=params)

    def get_prompt_data(
        self,
        dataset_id: str,
        resource_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        count: bool = True,
        prompt_contains: Optional[str] = None,
        response_contains: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch indexed data for a PROMPT-typed dataset.

        Same generic semantics as :meth:`get_dataset_data`, plus prompt-aware
        shorthands that automatically map to the underlying prompt/response/
        length columns when present:

        Args:
            prompt_contains: Substring (case-insensitive) match on the prompt
                column (auto-detects ``prompt``/``input``/``instruction``/
                ``question``).
            response_contains: Substring match on the response column
                (auto-detects ``response``/``completion``/``answer``/
                ``output``).
            min_length / max_length: Bounds on the length column
                (auto-detects ``length``/``prompt_length``/``tokens``/
                ``token_count``).

        The response includes ``prompt_column``, ``response_column``, and
        ``length_column`` indicating what was auto-detected.
        """
        params = self._build_data_params(filters, columns, order_by, limit, offset, count)
        if resource_id:
            params["resource_id"] = resource_id
        if prompt_contains is not None:
            params["prompt_contains"] = prompt_contains
        if response_contains is not None:
            params["response_contains"] = response_contains
        if min_length is not None:
            params["min_length"] = int(min_length)
        if max_length is not None:
            params["max_length"] = int(max_length)
        return self.get(f"/api/datasets/{dataset_id}/prompts/", params=params)

    def iter_resource_data(
        self,
        resource_id: str,
        filters: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
        batch_size: int = 1000,
    ) -> Iterator[Dict[str, Any]]:
        """Yield rows as dicts, paging through the entire filtered result set.

        Each yielded item is a ``{column: value}`` mapping. ``batch_size`` is
        capped at 10000 by the server.
        """
        offset = 0
        while True:
            page = self.get_resource_data(
                resource_id=resource_id,
                filters=filters,
                columns=columns,
                order_by=order_by,
                limit=batch_size,
                offset=offset,
                count=False,
            )
            cols: List[str] = page.get("columns", []) or []
            rows: List[List[Any]] = page.get("rows", []) or []
            if not rows:
                return
            for row in rows:
                yield dict(zip(cols, row))
            if len(rows) < batch_size:
                return
            offset += len(rows)
