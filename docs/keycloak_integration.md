# Keycloak Integration Documentation

## Overview

This document provides technical details on the Keycloak integration with the DataExchange platform. The integration uses python-keycloak 5.5.0 and focuses on runtime performance while maintaining flexibility in role management.

## Architecture

The DataExchange platform uses Keycloak for authentication while maintaining its own role-based authorization system. This hybrid approach allows for:

1. **Centralized Authentication**: Keycloak handles user authentication, token validation, and session management
2. **Custom Authorization**: DataExchange maintains its own role and permission models in the database
3. **Flexible Integration**: User data is synchronized from Keycloak but roles are managed within the application

## Environment Configuration

The following environment variables must be set for the Keycloak integration to work:

```
KEYCLOAK_SERVER_URL=https://your-keycloak-server/auth
KEYCLOAK_REALM=your-realm
KEYCLOAK_CLIENT_ID=your-client-id
KEYCLOAK_CLIENT_SECRET=your-client-secret
```

## Core Components

### KeycloakManager

The `KeycloakManager` class in `authorization/keycloak.py` is the central component that handles all Keycloak interactions. It provides methods for:

- Token validation
- User information retrieval
- User synchronization
- Role mapping

```python
# Example usage
from authorization.keycloak import keycloak_manager

# Validate a token
user_info = keycloak_manager.validate_token(token)

# Get user roles
roles = keycloak_manager.get_user_roles(token)

# Sync user from Keycloak
user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
```

### Authentication Middleware

The `KeycloakAuthenticationMiddleware` in `authorization/middleware.py` intercepts requests and authenticates users based on Keycloak tokens. It:

1. Extracts the token from either the `Authorization` header or `x-keycloak-token` header
2. Validates the token using the KeycloakManager
3. Retrieves or creates the user in the database
4. Attaches the user to the request

```python
# The middleware is added to MIDDLEWARE in settings.py
MIDDLEWARE = [
    # ...
    'authorization.middleware.KeycloakAuthenticationMiddleware',
    # ...
]
```

### Context Middleware

The `ContextMiddleware` in `api/utils/middleware.py` extracts additional context from requests, including:

- Authentication token
- Organization context
- Dataspace context

This middleware supports both standard OAuth Bearer tokens and custom Keycloak tokens via the `x-keycloak-token` header.

### Permission Classes

The system includes specialized permission classes for both REST and GraphQL APIs:

#### REST Permissions

REST permissions are defined in `authorization/permissions.py` and extend Django REST Framework's permission classes.

#### GraphQL Permissions

GraphQL permissions are defined in specialized classes that check user roles and permissions:

```python
class ViewDatasetPermission(DatasetPermissionGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="view")

class ChangeDatasetPermission(DatasetPermissionGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="change")
```

These classes are used in GraphQL resolvers to enforce permissions:

```python
@strawberry.field(
    permission_classes=[IsAuthenticated, ViewDatasetPermission],
)
def get_dataset(self, dataset_id: uuid.UUID) -> TypeDataset:
    # ...
```

## Authentication Flow

1. **Frontend Login**:
   - User authenticates with Keycloak directly
   - Frontend receives and stores the Keycloak token

2. **API Requests**:
   - Frontend includes the token in either:
     - `Authorization: Bearer <token>` header
     - `x-keycloak-token: <token>` header

3. **Token Validation**:
   - `KeycloakAuthenticationMiddleware` intercepts the request
   - Token is validated using `keycloak_manager.validate_token()`
   - User info is extracted from the token

4. **User Synchronization**:
   - User data is synchronized with the database
   - Roles and organization memberships are updated

5. **Permission Checking**:
   - Permission classes check if the user has the required role
   - Access is granted or denied based on the user's roles

## Role Management

Roles are managed within the DataExchange database rather than in Keycloak. The system includes:

1. **Role Model**: Defines permissions for viewing, adding, changing, and deleting resources
2. **OrganizationMembership**: Maps users to organizations with specific roles
3. **DatasetPermission**: Provides dataset-specific permissions

The `init_roles` management command initializes the default roles:

```bash
python manage.py init_roles
```

This creates the following default roles:
- **admin**: Full access (view, add, change, delete)
- **editor**: Can view, add, and change but not delete
- **viewer**: Read-only access

## Token Handling

The system supports two methods for sending tokens from the frontend:

1. **Standard OAuth Method**:
   ```
   Authorization: Bearer <token>
   ```

2. **Custom Header Method**:
   ```
   x-keycloak-token: <token>
   ```

Both methods are supported to provide flexibility in frontend implementation.

## Error Handling

The Keycloak integration includes robust error handling:

- Token validation errors return anonymous users
- User synchronization errors are logged
- Permission errors return appropriate HTTP status codes

## Security Considerations

1. **Token Validation**: All tokens are validated with Keycloak before granting access
2. **Role-Based Access Control**: Fine-grained permissions based on user roles
3. **Secure Headers**: CORS configuration allows only specific headers

## Troubleshooting

### Common Issues

1. **Token Validation Failures**:
   - Check Keycloak server URL and realm configuration
   - Verify token expiration
   - Ensure client secret is correct

2. **Permission Errors**:
   - Verify user has appropriate role assignments
   - Check organization memberships
   - Run `init_roles` command if roles are missing

3. **Migration Issues**:
   - If encountering migration dependency issues, use the techniques described in the migration section

## Performance Considerations

The implementation prioritizes runtime execution over strict type checking:

1. **Token Caching**: User information is cached to reduce Keycloak API calls
2. **Lazy Loading**: User data is loaded only when needed
3. **Type Ignores**: Strategic use of type ignores to maintain runtime functionality

## Extending the System

To extend the authorization system:

1. **Add New Roles**: Modify the `init_roles` command to include additional roles
2. **Custom Permissions**: Create new permission classes that extend existing ones
3. **Additional Context**: Extend the ContextMiddleware to include more context information

## Conclusion

The Keycloak integration provides a flexible, secure authentication system while maintaining custom authorization logic. By separating authentication from authorization, the system allows for fine-grained control over permissions while leveraging Keycloak's robust authentication capabilities.
