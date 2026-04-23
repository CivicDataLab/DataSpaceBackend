"""DEPRECATED: This module is deprecated. Use api.utils.keycloak_utils instead."""

# Import from the new location for backward compatibility
from api.utils.keycloak_utils import KeycloakManager, keycloak_manager

__all__ = ["KeycloakManager", "keycloak_manager"]
