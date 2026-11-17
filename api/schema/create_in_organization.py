"""Generated create mutations whose owner, organisation and status come from the server.

The inputs of `createUseCase`/`createCollaborative` list every model field.
Whatever the caller sends for these, the new item gets a new id and public id,
belongs to the caller and to the organisation in the request header (no header
means an individual item), and starts as a draft. Pair it with a
`CreateInOrganizationPermission` subclass.
"""

from typing import Any, List, Type

from strawberry.annotation import StrawberryAnnotation
from strawberry.permission import BasePermission
from strawberry.types import Info
from strawberry_django.mutations.fields import DjangoCreateMutation


class _CreateInOrganization(DjangoCreateMutation):
    draft_status: str

    def create(self, data: dict[str, Any], *, info: Info) -> Any:
        data.pop("id", None)
        data["public_id"] = ""  # empty: the model's save generates a fresh one
        data["user"] = info.context.user
        data["organization"] = info.context.context.get("organization")
        data["status"] = self.draft_status
        return super().create(data, info=info)


def create_in_organization(
    input_type: type,
    *,
    draft_status: str,
    permission_classes: List[Type[BasePermission]],
) -> Any:
    """`mutations.create(input_type)` with the owner, organisation and status set here."""
    field = _CreateInOrganization(
        input_type,
        python_name=None,
        django_name=None,
        graphql_name=None,
        type_annotation=StrawberryAnnotation.from_annotation(None),
        permission_classes=permission_classes,
        extensions=(),
    )
    field.draft_status = draft_status
    return field
