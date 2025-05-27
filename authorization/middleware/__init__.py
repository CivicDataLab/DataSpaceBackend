# Import middleware classes to expose them at the package level
from authorization.middleware.activity_consent import ActivityConsentMiddleware
from authorization.middleware.keycloak_auth import KeycloakAuthenticationMiddleware
