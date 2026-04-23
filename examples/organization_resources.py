"""Example: Working with organization resources."""

from typing import Any, List

from dataspace_sdk import DataSpaceClient

# Initialize and login
client = DataSpaceClient(base_url="https://api.dataspace.example.com")
keycloak_token = "your_keycloak_token_here"

try:
    user_info = client.login(keycloak_token=keycloak_token)
    print(f"Logged in as: {user_info['user']['username']}\n")

    # Iterate through user's organizations
    for org in user_info["user"]["organizations"]:
        print(f"Organization: {org['name']}")
        print(f"Role: {org['role']}")
        print("-" * 50)

        # Get datasets for this organization
        datasets = client.datasets.get_organization_datasets(organization_id=org["id"], limit=10)
        # Handle both list and dict responses
        datasets_list: List[Any] = datasets if isinstance(datasets, list) else []
        print(f"Datasets: {len(datasets_list)}")
        for dataset in datasets_list[:5]:
            print(f"  - {dataset['title']}")

        # Get AI models for this organization
        models = client.aimodels.get_organization_models(organization_id=org["id"], limit=10)
        # Handle both list and dict responses
        models_list: List[Any] = models if isinstance(models, list) else []
        print(f"\nAI Models: {len(models_list)}")
        for model in models_list[:5]:
            print(f"  - {model.get('displayName', model.get('name'))}")

        # Get use cases for this organization
        usecases = client.usecases.get_organization_usecases(organization_id=org["id"], limit=10)
        # Handle both list and dict responses
        usecases_list: List[Any] = usecases if isinstance(usecases, list) else []
        print(f"\nUse Cases: {len(usecases_list)}")
        for usecase in usecases_list[:5]:
            print(f"  - {usecase['title']}")

        print("\n")

except Exception as e:
    print(f"Error: {e}")
