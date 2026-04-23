# DataSpace Python SDK

A Python SDK for programmatic access to DataSpace resources including Datasets, AI Models, and Use Cases.

## Installation

### From PyPI (once published)

```bash
pip install dataspace-sdk
```

### From Source

```bash
git clone https://github.com/CivicDataLab/DataExchange.git
cd DataExchange/DataExBackend
pip install -e .
```

### For Development

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from dataspace_sdk import DataSpaceClient

# Initialize the client with Keycloak configuration
client = DataSpaceClient(
    base_url="https://dev.api.civicdataspace.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace",
    keycloak_client_secret="your_client_secret"
)

# Login with username and password
user_info = client.login(
    username="your_email@example.com",
    password="your_password"
)
print(f"Logged in as: {user_info['user']['username']}")

# Search for datasets
datasets = client.datasets.search(
    query="health data",
    tags=["public-health"],
    page=1,
    page_size=10
)

# Get a specific dataset
dataset = client.datasets.get_by_id("dataset-uuid")
print(f"Dataset: {dataset['title']}")

# Get organization's resources
if user_info['user']['organizations']:
    org_id = user_info['user']['organizations'][0]['id']
    org_datasets = client.datasets.get_organization_datasets(org_id)
```

## Features

- **Authentication**: Multiple authentication methods (username/password, Keycloak token, service account)
- **Automatic Token Management**: Automatic token refresh and re-login
- **Datasets**: Search, retrieve, and list datasets with filtering and pagination
- **AI Models**: Search, retrieve, call, and list AI models with filtering
- **Use Cases**: Search, retrieve, and list use cases with filtering
- **Organization Resources**: Get resources specific to your organizations
- **GraphQL & REST**: Supports both GraphQL and REST API endpoints
- **Error Handling**: Comprehensive exception handling with detailed error messages

## Authentication

The SDK supports three authentication methods:

### 1. Username and Password (Recommended for Users)

```python
from dataspace_sdk import DataSpaceClient

client = DataSpaceClient(
    base_url="https://dev.api.civicdataspace.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace",
    keycloak_client_secret="your_client_secret"
)

# Login with username and password
user_info = client.login(
    username="your_email@example.com",
    password="your_password"
)

# Access user information
print(user_info['user']['username'])
print(user_info['user']['organizations'])
```

### 2. Keycloak Token (For Token Pass-through)

```python
# Login with an existing Keycloak token
response = client.login_with_token(keycloak_token="your_keycloak_token")
```

### 3. Service Account (For Backend Services)

```python
# Login as a service account using client credentials
service_info = client.login_as_service_account()
```

For detailed authentication documentation, see [AUTHENTICATION_COMPLETE.md](./AUTHENTICATION_COMPLETE.md)

### Token Refresh

```python
# Refresh access token when it expires
new_token = client.refresh_token()
```

### Check Authentication Status

```python
if client.is_authenticated():
    print("Authenticated!")
    print(f"User: {client.user['username']}")
```

## Working with Datasets

### Search Datasets

```python
# Basic search
results = client.datasets.search(query="education")

# Advanced search with filters
results = client.datasets.search(
    query="health",
    tags=["public-health", "covid-19"],
    sectors=["Health"],
    geographies=["India", "Karnataka"],
    status="PUBLISHED",
    access_type="OPEN",
    sort="recent",
    page=1,
    page_size=20
)

# Access results
print(f"Total results: {results['total']}")
for dataset in results['results']:
    print(f"- {dataset['title']}")
```

### Get Dataset by ID

```python
# Get detailed dataset information
dataset = client.datasets.get_by_id("550e8400-e29b-41d4-a716-446655440000")

print(f"Title: {dataset['title']}")
print(f"Description: {dataset['description']}")
print(f"Organization: {dataset['organization']['name']}")
print(f"Resources: {len(dataset['resources'])}")
```

### List All Datasets

```python
# List with pagination
datasets = client.datasets.list_all(
    status="PUBLISHED",
    limit=50,
    offset=0
)

for dataset in datasets:
    print(f"- {dataset['title']}")
```

### Get Trending Datasets

```python
trending = client.datasets.get_trending(limit=10)
for dataset in trending['results']:
    print(f"- {dataset['title']} (views: {dataset['view_count']})")
```

### Get Organization Datasets

```python
# Get datasets for your organization
org_id = client.user['organizations'][0]['id']
org_datasets = client.datasets.get_organization_datasets(
    organization_id=org_id,
    limit=20,
    offset=0
)
```

## Working with AI Models

### Search AI Models

```python
# Basic search
results = client.aimodels.search(query="language model")

# Advanced search
results = client.aimodels.search(
    query="llm",
    tags=["nlp", "text-generation"],
    model_type="LLM",
    provider="OPENAI",
    status="ACTIVE",
    sort="recent",
    page=1,
    page_size=10
)
```

### Get AI Model by ID

```python
# Using REST endpoint
model = client.aimodels.get_by_id("model-uuid")

# Using GraphQL (more detailed)
model = client.aimodels.get_by_id_graphql("model-uuid")

print(f"Model: {model['displayName']}")
print(f"Type: {model['modelType']}")
print(f"Provider: {model['provider']}")
print(f"Endpoints: {len(model['endpoints'])}")
```

### Call an AI Model

```python
# Call an AI model with input text
result = client.aimodels.call_model(
    model_id="model-uuid",
    input_text="What is the capital of France?",
    parameters={
        "temperature": 0.7,
        "max_tokens": 100
    }
)

if result['success']:
    print(f"Output: {result['output']}")
    print(f"Latency: {result['latency_ms']}ms")
    print(f"Provider: {result['provider']}")
else:
    print(f"Error: {result['error']}")

# For long-running operations, use async call
task = client.aimodels.call_model_async(
    model_id="model-uuid",
    input_text="Generate a long document...",
    parameters={"max_tokens": 2000}
)
print(f"Task ID: {task['task_id']}")
print(f"Status: {task['status']}")
```

### List All AI Models

```python
models = client.aimodels.list_all(
    status="ACTIVE",
    model_type="LLM",
    limit=20,
    offset=0
)
```

### Get Organization AI Models

```python
org_id = client.user['organizations'][0]['id']
org_models = client.aimodels.get_organization_models(
    organization_id=org_id,
    limit=20,
    offset=0
)
```

## Working with Use Cases

### Search Use Cases

```python
# Basic search
results = client.usecases.search(query="health monitoring")

# Advanced search
results = client.usecases.search(
    query="covid",
    tags=["health", "monitoring"],
    sectors=["Health"],
    status="PUBLISHED",
    running_status="COMPLETED",
    sort="completed_on",
    page=1,
    page_size=10
)
```

### Get Use Case by ID

```python
# Get use case by ID
usecase = client.usecases.get_by_id(123)

print(f"Title: {usecase['title']}")
print(f"Summary: {usecase['summary']}")
print(f"Status: {usecase['runningStatus']}")
print(f"Datasets used: {len(usecase['datasets'])}")
print(f"Organizations: {len(usecase['organizations'])}")
```

### List All Use Cases

```python
usecases = client.usecases.list_all(
    status="PUBLISHED",
    running_status="COMPLETED",
    limit=20,
    offset=0
)
```

### Get Organization Use Cases

```python
org_id = client.user['organizations'][0]['id']
org_usecases = client.usecases.get_organization_usecases(
    organization_id=org_id,
    limit=20,
    offset=0
)
```

## Error Handling

```python
from dataspace_sdk import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)

try:
    dataset = client.datasets.get_by_id("invalid-uuid")
except DataSpaceNotFoundError as e:
    print(f"Dataset not found: {e.message}")
except DataSpaceAuthError as e:
    print(f"Authentication error: {e.message}")
    # Try to refresh token
    client.refresh_token()
except DataSpaceValidationError as e:
    print(f"Validation error: {e.message}")
    print(f"Details: {e.response}")
except DataSpaceAPIError as e:
    print(f"API error: {e.message}")
    print(f"Status code: {e.status_code}")
```

## Advanced Usage

### Pagination

```python
# Manual pagination
page = 1
page_size = 20
all_datasets = []

while True:
    results = client.datasets.search(
        query="health",
        page=page,
        page_size=page_size
    )

    all_datasets.extend(results['results'])

    if len(results['results']) < page_size:
        break

    page += 1

print(f"Total datasets fetched: {len(all_datasets)}")
```

### Working with Multiple Organizations

```python
# Get user's organizations
user_info = client.get_user_info()

for org in user_info['organizations']:
    print(f"\nOrganization: {org['name']} (Role: {org['role']})")

    # Get resources for each organization
    datasets = client.datasets.get_organization_datasets(org['id'])
    models = client.aimodels.get_organization_models(org['id'])
    usecases = client.usecases.get_organization_usecases(org['id'])

    print(f"  Datasets: {len(datasets)}")
    print(f"  AI Models: {len(models)}")
    print(f"  Use Cases: {len(usecases)}")
```

### Combining Search Results

```python
# Search across all resource types
query = "health"

datasets = client.datasets.search(query=query, page_size=5)
models = client.aimodels.search(query=query, page_size=5)
usecases = client.usecases.search(query=query, page_size=5)

print(f"Found {datasets['total']} datasets")
print(f"Found {models['total']} AI models")
print(f"Found {usecases['total']} use cases")
```

## API Reference

### DataSpaceClient

Main client for interacting with DataSpace API.

**Methods:**

- `login(username: str, password: str) -> dict`: Login with username and password
- `login_with_token(keycloak_token: str) -> dict`: Login with Keycloak token
- `login_as_service_account() -> dict`: Login as service account (client credentials)
- `refresh_token() -> str`: Refresh access token
- `get_user_info() -> dict`: Get current user information
- `is_authenticated() -> bool`: Check authentication status

**Properties:**

- `datasets`: DatasetClient instance
- `aimodels`: AIModelClient instance
- `usecases`: UseCaseClient instance
- `user`: Current user information
- `access_token`: Current access token

### DatasetClient

Client for dataset operations.

**Methods:**

- `search(...)`: Search datasets with filters
- `get_by_id(dataset_id: str)`: Get dataset by UUID (GraphQL)
- `list_all(...)`: List all datasets with pagination
- `get_trending(limit: int)`: Get trending datasets
- `get_organization_datasets(organization_id: str, ...)`: Get organization's datasets
- `get_resources(dataset_id: str)`: Get dataset resources
- `list_by_organization(organization_id: str, ...)`: List datasets by organization

### AIModelClient

Client for AI model operations.

**Methods:**

- `search(...)`: Search AI models with filters
- `get_by_id(model_id: str)`: Get AI model by UUID (REST)
- `get_by_id_graphql(model_id: str)`: Get AI model by UUID (GraphQL)
- `call_model(model_id: str, input_text: str, parameters: dict)`: Call an AI model
- `call_model_async(model_id: str, input_text: str, parameters: dict)`: Call an AI model asynchronously
- `list_all(...)`: List all AI models with pagination
- `get_organization_models(organization_id: str, ...)`: Get organization's AI models
- `create(data: dict)`: Create a new AI model
- `update(model_id: str, data: dict)`: Update an AI model
- `delete_model(model_id: str)`: Delete an AI model

### UseCaseClient

Client for use case operations.

**Methods:**

- `search(...)`: Search use cases with filters
- `get_by_id(usecase_id: int)`: Get use case by ID (GraphQL)
- `list_all(...)`: List all use cases with pagination
- `get_organization_usecases(organization_id: str, ...)`: Get organization's use cases

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

AGPL-3.0 License

## Support

For issues and questions, please open an issue on [GitHub](https://github.com/CivicDataLab/DataExchange/issues).
