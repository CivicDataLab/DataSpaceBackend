# mypy: disable-error-code=valid-type
# mypy: disable-error-code=override
# mypy: disable-error-code=misc
# mypy: disable-error-code=var-annotated
# mypy: disable-error-code=no-untyped-def
# mypy: disable-error-code=operator
# mypy: disable-error-code=arg-type
from typing import Any, Callable, Dict, Optional, Type, Union, cast

import strawberry
from django.db.models import Model
from strawberry.extensions import FieldExtension
from strawberry.types import Info

from authorization.activity import record_activity


class TrackActivity(FieldExtension):
    """
    Strawberry field extension to track activities for GraphQL operations.

    This extension can be added to any GraphQL field, but is most useful for mutations.
    It will track the activity when the field is resolved, using the current user as the actor.

    Example usage:

    ```python
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[TrackActivity(verb="created resource")]
    )
    def create_resource(self, info: Info, input: ResourceInput) -> TypeResource:
        # Your mutation code
        ...
    ```
    """

    def __init__(
        self,
        verb: str,
        get_action_object: Optional[Callable[[Any], Any]] = None,
        get_target: Optional[Callable[[Any], Any]] = None,
        get_data: Optional[Callable[[Any], Dict[str, Any]]] = None,
    ):
        """
        Initialize the extension.

        Args:
            verb: The verb describing the activity (e.g., 'created', 'updated')
            get_action_object: Function to extract the action object from the result
            get_target: Function to extract the target from the result
            get_data: Function to extract additional data
        """
        self.verb = verb
        self.get_action_object = get_action_object
        self.get_target = get_target
        self.get_data = get_data

    def resolve(self, next_, root, info: Info, **kwargs) -> Any:
        """
        Resolve the field and track the activity.
        """
        # Execute the resolver first
        result = next_(root, info, **kwargs)

        # Track the activity
        # In Strawberry GraphQL, info.context is the request object
        request = info.context
        user = (
            request.user
            if hasattr(request, "user") and request.user.is_authenticated
            else None
        )

        if user:
            # Get additional data
            data = self.get_data(result, **kwargs) if self.get_data else {}

            # Special handling for dataset deletion
            if self.verb == "deleted dataset" and "dataset_id" in kwargs:
                from api.activities.dataset import track_dataset_deleted

                # Extract dataset title if available in the data
                dataset_title = "Unknown Dataset"
                dataset_id = str(kwargs.get("dataset_id"))
                organization_id = None

                # Try to get additional data if provided
                if data and "dataset_title" in data:
                    dataset_title = data["dataset_title"]
                if data and "organization_id" in data:
                    organization_id = data["organization_id"]

                # Use the specialized tracking function
                track_dataset_deleted(
                    user=user,
                    dataset_id=dataset_id,
                    dataset_title=dataset_title,
                    organization_id=organization_id,
                    request=request,
                )
                return result

            # Special handling for resource deletion
            elif self.verb == "deleted resource" and "resource_id" in kwargs:
                from api.activities.resource import track_resource_deleted

                # Extract resource info if available in the data
                resource_name = "Unknown Resource"
                resource_id = str(kwargs.get("resource_id"))
                dataset_id = None
                dataset_title = "Unknown Dataset"

                # Try to get additional data if provided
                if data and "resource_name" in data:
                    resource_name = data["resource_name"]
                if data and "dataset_id" in data:
                    dataset_id = data["dataset_id"]
                if data and "dataset_title" in data:
                    dataset_title = data["dataset_title"]

                # Use the specialized tracking function
                track_resource_deleted(
                    user=user,
                    resource_id=resource_id,
                    resource_name=resource_name,
                    dataset_id=dataset_id,
                    dataset_title=dataset_title,
                    request=request,
                )
                return result

            # Special handling for usecase deletion
            elif self.verb == "deleted usecase" and "usecase_id" in kwargs:
                from api.activities.usecase import track_usecase_deleted

                # Extract usecase info if available in the data
                usecase_title = "Unknown Use Case"
                usecase_id = str(kwargs.get("usecase_id"))
                organization_id = None

                # Try to get additional data if provided
                if data and "usecase_title" in data:
                    usecase_title = data["usecase_title"]
                if data and "organization_id" in data:
                    organization_id = data["organization_id"]

                # Use the specialized tracking function
                track_usecase_deleted(
                    user=user,
                    usecase_id=usecase_id,
                    usecase_title=usecase_title,
                    organization_id=organization_id,
                    request=request,
                )
                return result

            # Standard handling for other operations
            # Get the action object and target
            action_object = (
                self.get_action_object(result) if self.get_action_object else None
            )
            target = self.get_target(result) if self.get_target else None

            # Get additional data
            data = self.get_data(result, **kwargs) if self.get_data else {}

            # Add default data if not provided
            if not data:
                data = {
                    "operation_name": info.field_name,
                    "arguments": {
                        k: str(v)
                        for k, v in kwargs.items()
                        if not isinstance(v, (dict, list))
                    },
                }

            # Record the activity
            record_activity(
                actor=user,
                verb=self.verb,
                action_object=action_object,
                target=target,
                request=request,
                data=data,
            )

        return result


class TrackModelActivity(TrackActivity):
    """
    Specialized extension for tracking activities on Django models.

    This extension is designed for mutations that create or update Django models.
    It automatically extracts the model instance from the result and uses it as the action object.
    It also detects the model type and calls the appropriate specialized tracking function when available.

    Example usage:

    ```python
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[TrackModelActivity(verb="created", model_attr="resource")]
    )
    def create_resource(self, info: Info, input: ResourceInput) -> TypeResource:
        # Your mutation code
        ...
    ```
    """

    def __init__(
        self,
        verb: str,
        model_attr: Optional[str] = None,
        target_attr: Optional[str] = None,
        get_data: Optional[Callable[[Any], Dict[str, Any]]] = None,
    ):
        """
        Initialize the extension.

        Args:
            verb: The verb describing the activity (e.g., 'created', 'updated')
            model_attr: Attribute name to get the model instance from the result
            target_attr: Attribute name to get the target from the result
            get_data: Function to extract additional data
        """
        self.model_attr = model_attr
        self.target_attr = target_attr
        self.verb = verb
        self.get_data_func = get_data

        # Define functions to extract the action object and target
        def get_action_object(result):
            if self.model_attr:
                return (
                    getattr(result, self.model_attr)
                    if hasattr(result, self.model_attr)
                    else result
                )
            return result

        def get_target(result):
            if self.target_attr:
                return (
                    getattr(result, self.target_attr)
                    if hasattr(result, self.target_attr)
                    else None
                )
            return None

        super().__init__(verb, get_action_object, get_target, get_data)

    def resolve(self, next_, root, info: Info, **kwargs) -> Any:
        """
        Override the resolve method to use specialized tracking functions when available.
        """
        # Execute the resolver first
        result = next_(root, info, **kwargs)

        # Check if we should track the activity
        # In Strawberry GraphQL, info.context is the request object
        request = info.context
        user = (
            request.user
            if hasattr(request, "user") and request.user.is_authenticated
            else None
        )

        if user:
            # Get additional data
            data = self.get_data_func(result, **kwargs) if self.get_data_func else {}

            # Check if this is a model operation
            if hasattr(result, "_django_instance"):
                django_instance = result._django_instance
                model_name = django_instance.__class__.__name__

                # Use the registry to handle the activity
                from api.activities.registry import handle_activity

                # Track the activity using the registry
                handle_activity(
                    model_name, self.verb, user, django_instance, data, request
                )
            else:
                # For non-model operations, record activity using parent's method
                action_object = (
                    self.get_action_object(result) if self.get_action_object else None
                )
                target = self.get_target(result) if self.get_target else None

                from authorization.activity import record_activity

                record_activity(
                    actor=user,
                    verb=self.verb,
                    action_object=action_object,
                    target=target,
                    request=request,
                    data=data,
                )

        return result
