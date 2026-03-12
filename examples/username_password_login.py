"""
Example: Login with username and password with automatic token refresh.

This example demonstrates:
1. Initializing the client with Keycloak configuration
2. Logging in with username and password
3. Automatic token refresh when tokens expire
4. Automatic re-login if refresh fails
"""

from dataspace_sdk import DataSpaceClient
from dataspace_sdk.exceptions import DataSpaceAuthError

# Initialize client with Keycloak configuration
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace",
    # keycloak_client_secret="your-secret"  # Only if using confidential client
)

# Login with username and password
# Credentials are stored securely for automatic re-login
try:
    user_info = client.login(username="your-email@example.com", password="your-password")
    print(f"✓ Logged in as: {user_info['user']['username']}")
    print(f"✓ Organizations: {[org['name'] for org in user_info['user'].get('organizations', [])]}")
except DataSpaceAuthError as e:
    print(f"✗ Login failed: {e}")
    exit(1)

# Now you can use the client normally
# Tokens will be automatically refreshed when they expire

# Example 1: Search datasets
print("\n--- Searching datasets ---")
datasets = client.datasets.search(query="health", page_size=5)
print(f"Found {len(datasets.get('results', []))} datasets")

# Example 2: Get user's organization datasets
print("\n--- Getting organization datasets ---")
user_orgs = user_info["user"].get("organizations", [])
if user_orgs:
    org_id = user_orgs[0]["id"]
    org_datasets = client.datasets.get_organization_datasets(org_id, limit=10, offset=0)
    print(f"Organization has datasets: {org_datasets}")

# Example 3: Token automatically refreshes
# Even if you use the client after tokens expire, it will auto-refresh
print("\n--- Simulating long-running session ---")
print("The SDK will automatically refresh tokens as needed...")

# You can also manually check authentication status
if client.is_authenticated():
    print("✓ Still authenticated")
else:
    print("✗ Not authenticated")

# Example 4: Get current user info (will auto-refresh if needed)
print("\n--- Getting user info ---")
try:
    current_user = client.get_user_info()
    print(f"Current user: {current_user.get('username')}")
except DataSpaceAuthError as e:
    print(f"Error: {e}")

print("\n✓ All operations completed successfully!")
print("Note: The SDK automatically handled token refresh and re-login as needed.")
