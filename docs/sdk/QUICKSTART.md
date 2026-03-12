# DataSpace SDK Quick Start Guide

Get started with the DataSpace Python SDK in 5 minutes!

## Installation

```bash
pip install dataspace-sdk
```

Or install from source:

```bash
git clone https://github.com/CivicDataLab/DataExchange.git
cd DataExchange/DataExBackend
pip install -e .
```

## Your First Script

```python
from dataspace_sdk import DataSpaceClient

# 1. Initialize the client with Keycloak configuration
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace"
)

# 2. Login with username and password
# Credentials are stored securely for automatic token refresh
user_info = client.login(
    username="your-email@example.com",
    password="your-password"
)
print(f"Logged in as: {user_info['user']['username']}")

# 3. Search for datasets (tokens auto-refresh as needed)
datasets = client.datasets.search(query="health", page_size=5)
print(f"Found {datasets['total']} datasets")

# 4. Get a specific dataset
dataset = client.datasets.get_by_id("dataset-uuid")
print(f"Dataset: {dataset['title']}")
```

### Alternative: Login with Pre-obtained Token

If you already have a Keycloak token:

```python
# Initialize without Keycloak config
client = DataSpaceClient(base_url="https://dataspace.civicdatalab.in")

# Login with token
client.login_with_token(keycloak_token="your_keycloak_token")
```

## Common Operations

### Search Resources

```python
# Search datasets
datasets = client.datasets.search(
    query="education",
    tags=["schools"],
    status="PUBLISHED"
)

# Search AI models
models = client.aimodels.search(
    query="language model",
    model_type="LLM"
)

# Search use cases
usecases = client.usecases.search(
    query="monitoring",
    running_status="COMPLETED"
)
```

### Get Organization Resources

```python
# Get your organizations
user_info = client.get_user_info()
org_id = user_info['organizations'][0]['id']

# Get organization's datasets
org_datasets = client.datasets.get_organization_datasets(org_id)

# Get organization's AI models
org_models = client.aimodels.get_organization_models(org_id)

# Get organization's use cases
org_usecases = client.usecases.get_organization_usecases(org_id)
```

### Handle Errors

```python
from dataspace_sdk import (
    DataSpaceAuthError,
    DataSpaceNotFoundError,
)

try:
    dataset = client.datasets.get_by_id("some-uuid")
except DataSpaceNotFoundError:
    print("Dataset not found")
except DataSpaceAuthError:
    print("Authentication failed, refreshing token...")
    client.refresh_token()
```

## Next Steps

- Read the [full documentation](README.md)
- Check out [examples](../../examples/)
- Learn about [development](DEVELOPMENT.md)

## Need Help?

- GitHub Issues: <https://github.com/CivicDataLab/DataExchange/issues>
- Email: info@civicdatalab.in
