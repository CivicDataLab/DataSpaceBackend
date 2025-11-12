"""Basic usage example for DataSpace SDK."""

from dataspace_sdk import DataSpaceClient

# Initialize the client
client = DataSpaceClient(base_url="https://api.dataspace.example.com")

# Login with Keycloak token
# Replace with your actual Keycloak token
keycloak_token = "your_keycloak_token_here"

try:
    user_info = client.login(keycloak_token=keycloak_token)
    print(f"✓ Logged in as: {user_info['user']['username']}")
    print(f"✓ Email: {user_info['user']['email']}")
    print(f"✓ Organizations: {len(user_info['user']['organizations'])}")

    # Search for datasets
    print("\n--- Searching for datasets ---")
    datasets = client.datasets.search(query="health", page=1, page_size=5)
    print(f"Found {datasets['total']} datasets")
    for dataset in datasets["results"][:3]:
        print(f"  - {dataset['title']}")

    # Get a specific dataset (replace with actual UUID)
    # dataset_id = "550e8400-e29b-41d4-a716-446655440000"
    # dataset = client.datasets.get_by_id(dataset_id)
    # print(f"\nDataset: {dataset['title']}")

    # Search for AI models
    print("\n--- Searching for AI models ---")
    models = client.aimodels.search(query="language", page=1, page_size=5)
    print(f"Found {models['total']} AI models")
    for model in models["results"][:3]:
        print(f"  - {model.get('displayName', model.get('name'))}")

    # Search for use cases
    print("\n--- Searching for use cases ---")
    usecases = client.usecases.search(query="monitoring", page=1, page_size=5)
    print(f"Found {usecases['total']} use cases")
    for usecase in usecases["results"][:3]:
        print(f"  - {usecase['title']}")

except Exception as e:
    print(f"Error: {e}")
