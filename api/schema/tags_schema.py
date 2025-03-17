import strawberry
import strawberry_django
from strawberry.types import Info

from api.models import Tag


@strawberry.type
class DeleteTagResponse:
    """Response for delete_tag mutation."""

    success: bool
    message: str


@strawberry.type
class Mutation:
    """Mutations for tags."""

    @strawberry_django.mutation(handle_django_errors=True)
    def delete_tag(self, info: Info, tag_id: str) -> DeleteTagResponse:
        """Delete a tag."""
        try:
            tag = Tag.objects.get(id=tag_id)
        except Tag.DoesNotExist:
            raise ValueError(f"Tag with ID {tag_id} does not exist.")
        tag.delete()
        return DeleteTagResponse(success=True, message="Tag deleted successfully")
