"""Example: Error handling and token refresh."""

from dataspace_sdk import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceClient,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)

# Initialize client
client = DataSpaceClient(base_url="https://api.dataspace.example.com")
keycloak_token = "your_keycloak_token_here"

# Login with error handling
try:
    user_info = client.login(keycloak_token=keycloak_token)
    print(f"✓ Logged in as: {user_info['user']['username']}")
except DataSpaceAuthError as e:
    print(f"✗ Authentication failed: {e.message}")
    print(f"  Status code: {e.status_code}")
    exit(1)

# Get dataset with error handling
dataset_id = "550e8400-e29b-41d4-a716-446655440000"

try:
    dataset = client.datasets.get_by_id(dataset_id)
    print(f"\n✓ Found dataset: {dataset['title']}")

except DataSpaceNotFoundError as e:
    print(f"\n✗ Dataset not found: {e.message}")
    print(f"  Dataset ID: {dataset_id}")

except DataSpaceAuthError as e:
    print(f"\n✗ Authentication error: {e.message}")
    print("  Attempting to refresh token...")

    try:
        new_token = client.refresh_token()
        print("  ✓ Token refreshed successfully")

        # Retry the request
        dataset = client.datasets.get_by_id(dataset_id)
        print(f"  ✓ Found dataset: {dataset['title']}")

    except DataSpaceAuthError as refresh_error:
        print(f"  ✗ Token refresh failed: {refresh_error.message}")
        print("  Please login again")

except DataSpaceValidationError as e:
    print(f"\n✗ Validation error: {e.message}")
    print(f"  Details: {e.response}")

except DataSpaceAPIError as e:
    print(f"\n✗ API error: {e.message}")
    print(f"  Status code: {e.status_code}")
    print(f"  Response: {e.response}")

# Search with error handling
try:
    results = client.datasets.search(
        query="test", status="INVALID_STATUS"  # This might cause a validation error
    )
    print(f"\n✓ Found {results['total']} datasets")

except DataSpaceValidationError as e:
    print(f"\n✗ Invalid search parameters: {e.message}")
    print(f"  Response: {e.response}")

except DataSpaceAPIError as e:
    print(f"\n✗ Search failed: {e.message}")

# Check authentication status
if client.is_authenticated():
    print("\n✓ Client is authenticated")
    if client.user:
        print(f"  User: {client.user['username']}")
        print(f"  Organizations: {len(client.user['organizations'])}")
else:
    print("\n✗ Client is not authenticated")

# Graceful error handling for network issues
try:
    # This will fail if the API is unreachable
    trending = client.datasets.get_trending(limit=5)
    if trending and "results" in trending:
        print(f"\n✓ Found {len(trending['results'])} trending datasets")

except DataSpaceAPIError as e:
    if "Network error" in str(e):
        print("\n✗ Network error: Unable to reach the API")
        print("  Please check your internet connection and API URL")
    else:
        print(f"\n✗ API error: {e.message}")
