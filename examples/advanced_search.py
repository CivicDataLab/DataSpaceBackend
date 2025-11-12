"""Example: Advanced search with filters and pagination."""

from dataspace_sdk import DataSpaceClient

# Initialize and login
client = DataSpaceClient(base_url="https://api.dataspace.example.com")
keycloak_token = "your_keycloak_token_here"

try:
    client.login(keycloak_token=keycloak_token)

    # Advanced dataset search with multiple filters
    print("=== Advanced Dataset Search ===\n")
    datasets = client.datasets.search(
        query="health data",
        tags=["public-health", "covid-19"],
        sectors=["Health", "Social Welfare"],
        geographies=["India", "Karnataka"],
        status="PUBLISHED",
        access_type="OPEN",
        sort="recent",
        page=1,
        page_size=10,
    )

    print(f"Total results: {datasets['total']}")
    print(f"Page: {datasets['page']} of {datasets['total_pages']}")
    print("\nResults:")
    for dataset in datasets["results"]:
        print(f"\n- Title: {dataset['title']}")
        print(f"  Status: {dataset['status']}")
        print(f"  Access: {dataset['access_type']}")
        print(f"  Tags: {', '.join([t['value'] for t in dataset.get('tags', [])])}")

    # Advanced AI model search
    print("\n\n=== Advanced AI Model Search ===\n")
    models = client.aimodels.search(
        query="language model",
        tags=["nlp", "text-generation"],
        model_type="LLM",
        provider="OPENAI",
        status="ACTIVE",
        sort="recent",
        page=1,
        page_size=10,
    )

    print(f"Total results: {models['total']}")
    print("\nResults:")
    for model in models["results"]:
        print(f"\n- Name: {model.get('displayName', model.get('name'))}")
        print(f"  Type: {model.get('modelType')}")
        print(f"  Provider: {model.get('provider')}")
        print(f"  Status: {model.get('status')}")

    # Advanced use case search
    print("\n\n=== Advanced Use Case Search ===\n")
    usecases = client.usecases.search(
        query="health monitoring",
        tags=["health", "monitoring", "real-time"],
        sectors=["Health"],
        status="PUBLISHED",
        running_status="COMPLETED",
        sort="completed_on",
        page=1,
        page_size=10,
    )

    print(f"Total results: {usecases['total']}")
    print("\nResults:")
    for usecase in usecases["results"]:
        print(f"\n- Title: {usecase['title']}")
        print(f"  Status: {usecase['status']}")
        print(f"  Running Status: {usecase.get('running_status')}")
        print(f"  Started: {usecase.get('started_on')}")
        print(f"  Completed: {usecase.get('completed_on')}")

    # Pagination example - fetch all results
    print("\n\n=== Pagination Example ===\n")
    all_datasets = []
    page = 1
    page_size = 20

    while True:
        results = client.datasets.search(query="education", page=page, page_size=page_size)

        all_datasets.extend(results["results"])
        print(f"Fetched page {page}: {len(results['results'])} results")

        if len(results["results"]) < page_size:
            break

        page += 1

    print(f"\nTotal datasets fetched: {len(all_datasets)}")

except Exception as e:
    print(f"Error: {e}")
