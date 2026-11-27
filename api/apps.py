from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self) -> None:
        # Before any GraphQL type is defined: file fields must not read a local path (#284)
        from api.types.file_types import use_storage_file_types

        use_storage_file_types()

        # Import signals to register them
        import api.signals

        # Registers the query engine's start-up check on the reranker setting.
        import api.services.query_engine.reranker  # noqa: F401
