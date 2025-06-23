from typing import List, Type

from actstream import registry
from django.apps import apps
from django.db.models import Model


def register_models() -> None:
    """
    Register models with activity stream.
    This function should be called in the AppConfig.ready() method.
    """
    # Register the User model
    User = apps.get_model("authorization", "User")
    registry.register(User)

    # Register Organization model
    Organization = apps.get_model("api", "Organization")
    registry.register(Organization)

    # Register Dataset model
    Dataset = apps.get_model("api", "Dataset")
    registry.register(Dataset)

    # Register UseCase model
    UseCase = apps.get_model("api", "UseCase")
    registry.register(UseCase)

    # Register Resource model
    Resource = apps.get_model("api", "Resource")
    registry.register(Resource)

    # Register UseCaseOrganizationRelationship model
    UseCaseOrganizationRelationship = apps.get_model(
        "api", "UseCaseOrganizationRelationship"
    )
    registry.register(UseCaseOrganizationRelationship)


def register_custom_models(model_list: List[Type[Model]]) -> None:
    """
    Register custom models with activity stream.

    Args:
        model_list: A list of model classes to register
    """
    for model in model_list:
        registry.register(model)
