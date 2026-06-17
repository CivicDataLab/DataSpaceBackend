"""
Test settings for Django tests.
"""

import os
import sys

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from DataSpace.settings import *

# Use an in-memory SQLite database for testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable debug mode
DEBUG = True

# Use a faster password hasher during tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Disable migrations during tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Disable celery tasks during tests
CELERY_ALWAYS_EAGER = True
CELERY_EAGER_PROPAGATES_EXCEPTIONS = True

# NOTE: We intentionally do NOT override INSTALLED_APPS — the real settings
# already define AUTH_USER_MODEL = "authorization.User", so the
# ``authorization`` app must be present for Django to bootstrap. Trimming the
# list to a "minimal" set previously broke every test with
# ``ImproperlyConfigured: AUTH_USER_MODEL refers to model 'authorization.User'
# that has not been installed``. Use ``MIGRATION_MODULES`` above to keep
# tests fast instead of stripping apps.

# Drop middleware that requires live external services (Keycloak / rate
# limiter / activity stream) so unit tests can boot without network access.
MIDDLEWARE = [
    m
    for m in MIDDLEWARE  # noqa: F405 — imported via ``from DataSpace.settings import *``
    if m
    not in {
        "authorization.middleware.KeycloakAuthenticationMiddleware",
        "authorization.middleware.activity_consent.ActivityConsentMiddleware",
        "api.middleware.rate_limit.rate_limit_middleware",
        "api.middleware.request_validator.RequestValidationMiddleware",
    }
]

# Elasticsearch is optional during unit tests — point the DSL at a dummy host
# so module import doesn't try to connect.
ELASTICSEARCH_DSL = {
    "default": {"hosts": "localhost:9200"},
}

# Disable real Keycloak calls in tests.
KEYCLOAK_SERVER_URL = "http://localhost:8080"
KEYCLOAK_REALM = "test"
KEYCLOAK_CLIENT_ID = "test-client"
KEYCLOAK_CLIENT_SECRET = "test-secret"
