# mypy: disable-error-code=no-untyped-def
from django.apps import AppConfig


class AuthorizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authorization"

    def ready(self):
        # Import and register models with activity stream
        try:
            from authorization.activity_registry import register_models

            register_models()
        except ImportError:
            # This prevents issues during migrations when models might not be available yet
            pass
