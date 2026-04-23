# DataSpace SDK Authentication Guide

This guide explains how to authenticate with the DataSpace SDK using username/password with automatic token management.

## Table of Contents

- [Quick Start](#quick-start)
- [Authentication Methods](#authentication-methods)
- [Automatic Token Management](#automatic-token-management)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

## Quick Start

### Username/Password Login (Recommended)

```python
from dataspace_sdk import DataSpaceClient

# Initialize with Keycloak configuration
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace"
)

# Login once - credentials stored for auto-refresh
user_info = client.login(
    username="your-email@example.com",
    password="your-password"
)

# Now use the client - tokens auto-refresh!
datasets = client.datasets.search(query="health")
```

## Authentication Methods

### 1. Username/Password (Recommended)

Best for:
- Scripts and automation
- Long-running applications
- Development and testing

```python
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace"
)

user_info = client.login(
    username="user@example.com",
    password="secret"
)
```

**Features:**
- ✅ Automatic token refresh
- ✅ Automatic re-login if refresh fails
- ✅ No manual token management needed
- ✅ Credentials stored securely in memory

### 2. Pre-obtained Keycloak Token

Best for:
- When you already have a token from another source
- Browser-based applications
- SSO integrations

```python
client = DataSpaceClient(base_url="https://dataspace.civicdatalab.in")

user_info = client.login_with_token(keycloak_token="eyJhbGci...")
```

**Note:** This method does NOT support automatic token refresh or re-login.

## Automatic Token Management

The SDK automatically handles token expiration and refresh:

### How It Works

1. **Login**: You provide username/password once
2. **Token Storage**: SDK stores credentials securely in memory
3. **Auto-Refresh**: When token expires (within 30 seconds), SDK automatically refreshes it
4. **Auto-Relogin**: If refresh fails, SDK automatically re-authenticates with stored credentials
5. **Transparent**: All of this happens automatically - you don't need to do anything!

### Example: Long-Running Script

```python
import time
from dataspace_sdk import DataSpaceClient

client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace"
)

# Login once
client.login(username="user@example.com", password="secret")

# Run for hours - tokens auto-refresh!
while True:
    datasets = client.datasets.search(query="health")
    print(f"Found {len(datasets.get('results', []))} datasets")

    # Sleep for 10 minutes
    time.sleep(600)

    # SDK automatically refreshes tokens as needed
    # No manual intervention required!
```

## Configuration

### Keycloak Configuration

You need these details from your Keycloak setup:

```python
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",          # DataSpace API URL
    keycloak_url="https://opub-kc.civicdatalab.in",        # Keycloak server URL
    keycloak_realm="DataSpace",                             # Realm name
    keycloak_client_id="dataspace",                         # Client ID
    keycloak_client_secret="optional-secret"                # Only for confidential clients
)
```

### Finding Your Keycloak Details

1. **Keycloak URL**: Your Keycloak server address
2. **Realm**: Usually shown in Keycloak admin console
3. **Client ID**: Found in Keycloak → Clients → Your Client
4. **Client Secret**: Only needed if client is "confidential" (check Access Type in Keycloak)

### Environment Variables (Recommended)

Store credentials securely:

```python
import os
from dataspace_sdk import DataSpaceClient

client = DataSpaceClient(
    base_url=os.getenv("DATASPACE_API_URL"),
    keycloak_url=os.getenv("KEYCLOAK_URL"),
    keycloak_realm=os.getenv("KEYCLOAK_REALM"),
    keycloak_client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    keycloak_client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET")  # Optional
)

client.login(
    username=os.getenv("DATASPACE_USERNAME"),
    password=os.getenv("DATASPACE_PASSWORD")
)
```

Create a `.env` file:

```bash
DATASPACE_API_URL=https://dataspace.civicdatalab.in
KEYCLOAK_URL=https://opub-kc.civicdatalab.in
KEYCLOAK_REALM=DataSpace
KEYCLOAK_CLIENT_ID=dataspace
DATASPACE_USERNAME=your-email@example.com
DATASPACE_PASSWORD=your-password
```

## Error Handling

### Authentication Errors

```python
from dataspace_sdk import DataSpaceClient
from dataspace_sdk.exceptions import DataSpaceAuthError

client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace"
)

try:
    user_info = client.login(
        username="user@example.com",
        password="wrong-password"
    )
except DataSpaceAuthError as e:
    print(f"Login failed: {e}")
    print(f"Status code: {e.status_code}")
    print(f"Response: {e.response}")
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Keycloak configuration missing` | Missing keycloak_url, realm, or client_id | Provide all required Keycloak parameters |
| `Keycloak login failed: invalid_grant` | Wrong username/password | Check credentials |
| `Keycloak login failed: invalid_client` | Wrong client_id or client requires consent | Check client_id or disable consent in Keycloak |
| `Resource not found` | Wrong Keycloak URL or realm | Verify keycloak_url and realm name |
| `Not authenticated` | Trying to use API before login | Call `client.login()` first |

### Checking Authentication Status

```python
# Check if authenticated
if client.is_authenticated():
    print("Authenticated!")
else:
    print("Not authenticated")

# Get current user info
user = client.user
if user:
    print(f"Logged in as: {user['username']}")
```

## Best Practices

### 1. Use Environment Variables

Never hardcode credentials:

```python
# ❌ Bad
client.login(username="user@example.com", password="secret123")

# ✅ Good
client.login(
    username=os.getenv("DATASPACE_USERNAME"),
    password=os.getenv("DATASPACE_PASSWORD")
)
```

### 2. Login Once, Use Everywhere

```python
# ✅ Good - Login once at startup
client = DataSpaceClient(...)
client.login(username=..., password=...)

# Use client throughout your application
# Tokens auto-refresh!
datasets = client.datasets.search(...)
models = client.aimodels.search(...)
```

### 3. Handle Errors Gracefully

```python
from dataspace_sdk.exceptions import DataSpaceAuthError

try:
    client.login(username=username, password=password)
except DataSpaceAuthError as e:
    logger.error(f"Authentication failed: {e}")
    # Handle error appropriately
    sys.exit(1)
```

### 4. Use Confidential Clients for Production

For production applications, use a confidential client with client_secret:

```python
client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace-prod",
    keycloak_client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET")
)
```

### 5. Don't Store Passwords in Code

```python
# ❌ Bad
PASSWORD = "secret123"

# ✅ Good - Use environment variables
password = os.getenv("DATASPACE_PASSWORD")

# ✅ Better - Use secrets management
from your_secrets_manager import get_secret
password = get_secret("dataspace_password")
```

## Advanced Usage

### Manual Token Refresh

While automatic refresh is recommended, you can manually refresh:

```python
# Get new access token
new_token = client.refresh_token()
print(f"New token: {new_token}")
```

### Get Current Access Token

```python
# Get current token (e.g., to pass to another service)
token = client.access_token
print(f"Current token: {token}")
```

### Ensure Authentication

Force authentication check and auto-relogin if needed:

```python
# This will auto-relogin if not authenticated
client._auth.ensure_authenticated()
```

## Troubleshooting

### Token Keeps Expiring

If you're experiencing frequent token expiration:

1. **Check token lifetime**: Keycloak admin → Realm Settings → Tokens → Access Token Lifespan
2. **Verify auto-refresh**: SDK automatically refreshes 30 seconds before expiration
3. **Check credentials**: Ensure username/password are stored correctly

### "Resource not found" Error

This usually means wrong Keycloak URL:

```python
# Try with /auth prefix
keycloak_url="https://opub-kc.civicdatalab.in/auth"

# Or without
keycloak_url="https://opub-kc.civicdatalab.in"

# Test in browser:
# https://opub-kc.civicdatalab.in/auth/realms/DataSpace/.well-known/openid-configuration
```

### "Client requires user consent" Error

In Keycloak admin console:

1. Go to Clients → your client
2. Find "Consent Required" setting
3. Set to OFF
4. Save

## Next Steps

- [Quick Start Guide](QUICKSTART.md)
- [Full SDK Documentation](README.md)
- [Examples](../../examples/)
- [API Reference](API_REFERENCE.md)
