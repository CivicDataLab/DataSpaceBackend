# Keycloak settings for Django integration

import os

from decouple import config

# Keycloak server settings
KEYCLOAK_SERVER_URL = config(
    "KEYCLOAK_SERVER_URL", default="http://localhost:8080/auth/"
)
KEYCLOAK_REALM = config("KEYCLOAK_REALM", default="dataexchange")
KEYCLOAK_CLIENT_ID = config("KEYCLOAK_CLIENT_ID", default="dataexchange-backend")
KEYCLOAK_CLIENT_SECRET = config("KEYCLOAK_CLIENT_SECRET", default="")

# Keycloak client settings
KEYCLOAK_CLIENT_PUBLIC_KEY = config("KEYCLOAK_CLIENT_PUBLIC_KEY", default="")
KEYCLOAK_CLIENT_SERVER_URL = config(
    "KEYCLOAK_CLIENT_SERVER_URL", default=KEYCLOAK_SERVER_URL
)
KEYCLOAK_CLIENT_REALM = config("KEYCLOAK_CLIENT_REALM", default=KEYCLOAK_REALM)
KEYCLOAK_CLIENT_CLIENT_ID = config(
    "KEYCLOAK_CLIENT_CLIENT_ID", default=KEYCLOAK_CLIENT_ID
)

# Keycloak admin credentials for user management
KEYCLOAK_ADMIN_USERNAME = config("KEYCLOAK_ADMIN_USERNAME", default="")
KEYCLOAK_ADMIN_PASSWORD = config("KEYCLOAK_ADMIN_PASSWORD", default="")

# Keycloak authorization settings
KEYCLOAK_AUTHORIZATION_CONFIG = {
    "KEYCLOAK_SERVER_URL": KEYCLOAK_SERVER_URL,
    "KEYCLOAK_REALM": KEYCLOAK_REALM,
    "KEYCLOAK_CLIENT_ID": KEYCLOAK_CLIENT_ID,
    "KEYCLOAK_CLIENT_SECRET": KEYCLOAK_CLIENT_SECRET,
}

# JWT Authentication settings
SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
}

# Django REST Framework JWT settings
REST_FRAMEWORK_JWT = {
    "JWT_AUTH_HEADER_PREFIX": "Bearer",
    "JWT_ALGORITHM": "RS256",
    "JWT_AUDIENCE": KEYCLOAK_CLIENT_ID,
    "JWT_ISSUER": f"{KEYCLOAK_SERVER_URL}realms/{KEYCLOAK_REALM}",
    "JWT_AUTH_COOKIE": "jwt-auth",
}
