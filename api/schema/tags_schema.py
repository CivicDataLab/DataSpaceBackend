import strawberry
import strawberry_django
from strawberry.types import Info

from api.models import Tag


@strawberry.type
class Mutation:
    """Mutations for tags."""

    @strawberry_django.mutation(handle_django_errors=True)
    def delete_tag(self, info: Info, tag_id: str) -> bool:
        """Delete a tag."""
        try:
            tag = Tag.objects.get(id=tag_id)
        except Tag.DoesNotExist:
            raise ValueError(f"Tag with ID {tag_id} does not exist.")
        tag.delete()
        return True
