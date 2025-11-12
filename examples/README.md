# DataSpace SDK Examples

This directory contains example scripts demonstrating how to use the DataSpace Python SDK.

## Prerequisites

1. Install the SDK:

   ```bash
   pip install dataspace-sdk
   # or for development
   pip install -e ..
   ```

2. Get a Keycloak token from your DataSpace instance

3. Update the examples with:
   - Your API base URL
   - Your Keycloak token

## Examples

### 1. basic_usage.py

Demonstrates basic SDK operations:

- Login with Keycloak
- Search datasets, AI models, and use cases
- Display results

**Run:**

```bash
python basic_usage.py
```

### 2. organization_resources.py

Shows how to work with organization-specific resources:

- Get user's organizations
- Fetch datasets, models, and use cases for each organization
- Display organization statistics

**Run:**

```bash
python organization_resources.py
```

### 3. advanced_search.py

Demonstrates advanced search capabilities:

- Complex filters (tags, sectors, geographies, status)
- Multiple search parameters
- Pagination
- Fetching all results

**Run:**

```bash
python advanced_search.py
```

### 4. error_handling.py

Shows proper error handling:

- Custom exception handling
- Token refresh on authentication errors
- Network error handling
- Graceful degradation

**Run:**

```bash
python error_handling.py
```

## Customization

Before running the examples, update these variables:

```python
# API base URL
base_url = "https://api.dataspace.example.com"

# Your Keycloak token
keycloak_token = "your_keycloak_token_here"

# Resource IDs (for get_by_id operations)
dataset_id = "your-dataset-uuid"
model_id = "your-model-uuid"
usecase_id = 123  # Use case ID
```

## Common Issues

### Authentication Errors

If you get authentication errors:

1. Verify your Keycloak token is valid
2. Check if the token has expired
3. Ensure you have the correct base URL

### Connection Errors

If you can't connect to the API:

1. Verify the base URL is correct
2. Check if the API is running
3. Verify network connectivity

### Not Found Errors

If resources are not found:

1. Verify the resource ID is correct
2. Check if you have permission to access the resource
3. Ensure the resource exists in the system

## Next Steps

- Read the [full documentation](../docs/sdk/README.md)
- Check the [development guide](../docs/sdk/DEVELOPMENT.md)
- Review the [quick start guide](../docs/sdk/QUICKSTART.md)
