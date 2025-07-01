import strawberry
import strawberry_django
from strawberry.types import Info

from api.models import Tag
from api.schema.base_mutation import (
    BaseMutation,
    DjangoValidationError,
    MutationResponse,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.permissions import IsAuthenticated


@strawberry.type
class Mutation:
    """Mutations for tags."""

    @strawberry_django.mutation(
        handle_django_errors=False, permission_classes=[IsAuthenticated]
    )
    @trace_resolver(
        name="delete_tag", attributes={"component": "tag", "operation": "mutation"}
    )
    def delete_tag(self, info: Info, tag_id: str) -> bool:
        """Delete a tag."""
        try:
            tag = Tag.objects.get(id=tag_id)
        except Tag.DoesNotExist:
            raise ValueError(f"Tag with ID {tag_id} does not exist.")
        tag.delete()
        return True

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_tags",
        trace_attributes={"component": "tag"},
    )
    def delete_tags(self, info: Info, tag_ids: list[str]) -> MutationResponse[bool]:
        """Delete multiple tags."""

        tags = Tag.objects.filter(id__in=tag_ids)
        if not tags.exists():
            raise DjangoValidationError(f"Tags with IDs {tag_ids} do not exist.")
        tags.delete()
        return MutationResponse.success_response(True)
