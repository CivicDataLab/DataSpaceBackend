# DataSpace SDK Overview

## What is the DataSpace SDK?

The DataSpace Python SDK provides programmatic access to DataSpace resources including Datasets, AI Models, and Use Cases. It's designed for developers who want to integrate DataSpace functionality into their applications without being confined to the frontend interface.

## Key Features

- **Authentication**: Keycloak token-based authentication with automatic token refresh
- **Read Operations**: Full read access to Datasets, AI Models, and Use Cases
- **Search**: Elasticsearch-powered search with advanced filtering
- **Organization Resources**: Access resources specific to your organizations
- **Error Handling**: Comprehensive exception hierarchy for robust error handling
- **Type Safety**: Type hints for better IDE support

## Quick Links

- **[Installation & Quick Start](QUICKSTART.md)** - Get started in 5 minutes
- **[Full Documentation](README.md)** - Complete API reference and usage examples
- **[Development Guide](DEVELOPMENT.md)** - Build, test, and publish the SDK

## Installation

```bash
pip install dataspace-sdk
```

Or install from source:

```bash
cd DataExBackend
pip install -e .
```

## Basic Usage

```python
from dataspace_sdk import DataSpaceClient

# Initialize and login
client = DataSpaceClient(base_url="https://api.dataspace.example.com")
client.login(keycloak_token="your_token")

# Search datasets
datasets = client.datasets.search(query="health", tags=["public-health"])

# Get organization resources
org_id = client.user['organizations'][0]['id']
org_datasets = client.datasets.get_organization_datasets(org_id)
```

## Available Operations

### Datasets

- Search with filters (tags, sectors, geographies, status, access_type)
- Get by UUID
- List all with pagination
- Get trending datasets
- Get organization-specific datasets

### AI Models

- Search with filters (tags, sectors, model_type, provider, status)
- Get by UUID
- List all with pagination
- Get organization-specific models

### Use Cases

- Search with filters (tags, sectors, status, running_status)
- Get by ID
- List all with pagination
- Get organization-specific use cases

## Examples

Check out the [examples](../../examples/) directory for:

- Basic usage
- Organization resources
- Advanced search with filters
- Error handling patterns

## License

AGPL-3.0 License

## Support

- **GitHub**: <https://github.com/CivicDataLab/DataExchange>
- **Issues**: <https://github.com/CivicDataLab/DataExchange/issues>
- **Email**: <tech@civicdatalab.in>
