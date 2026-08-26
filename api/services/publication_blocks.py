"""
publication_blocks
──────────────────
The messy 90% behind a Resource's content blocks: adding a file or YouTube
block at the next position, replacing a block's file without leaking the old
one, removing a block and renumbering the rest contiguously, reordering, and
the read-time access gate for a block's file.

Every write keeps ``position`` a dense 0..n-1 sequence, and every file swap or
removal deletes the previous bytes from disk so drafts don't leak files.
"""

from typing import Any, List

from django.core.exceptions import ValidationError
from django.db import transaction

from api.models import Publication, PublicationBlock
from api.services.publication_service import is_publication_published
from api.utils.enums import PublicationBlockType
from api.utils.publication_uploads import validate_publication_file
from api.utils.youtube import validate_youtube_url


def add_file_block(publication: Publication, uploaded_file: Any) -> PublicationBlock:
    """Validate an uploaded file and append it as the next content block."""
    extension, size = validate_publication_file(uploaded_file)

    block = PublicationBlock(
        publication=publication,
        position=_next_position(publication),
        block_type=PublicationBlockType.FILE,
        file_name=getattr(uploaded_file, "name", ""),
        file_format=extension.lstrip("."),
        file_size=size,
    )
    block.file = uploaded_file
    block.save()
    return block


def add_youtube_block(publication: Publication, youtube_url: str) -> PublicationBlock:
    """Validate a YouTube url and append it as the next content block."""
    video_id = validate_youtube_url(youtube_url)

    return PublicationBlock.objects.create(
        publication=publication,
        position=_next_position(publication),
        block_type=PublicationBlockType.YOUTUBE,
        youtube_url=youtube_url,
        youtube_video_id=video_id,
    )


def replace_block_file(block: PublicationBlock, uploaded_file: Any) -> PublicationBlock:
    """Swap a file block's file for a new one, deleting the old bytes from disk.

    Django's FileField never removes the previous file on reassignment, so we
    delete it explicitly first — a re-upload updates in place (same row id) and
    doesn't leak the old file.
    """
    if block.block_type != PublicationBlockType.FILE:
        raise ValidationError("Only a file block's file can be replaced.")

    extension, size = validate_publication_file(uploaded_file)

    # Drop the previous file from storage before attaching the new one.
    if block.file:
        block.file.delete(save=False)

    block.file = uploaded_file
    block.file_name = getattr(uploaded_file, "name", "")
    block.file_format = extension.lstrip(".")
    block.file_size = size
    block.save()
    return block


def remove_block(block: PublicationBlock) -> None:
    """Delete a block and renumber its siblings so positions stay contiguous."""
    publication = block.publication
    with transaction.atomic():
        block.delete()
        _renumber_blocks(publication)


def reorder_blocks(
    publication: Publication, ordered_block_ids: List[Any]
) -> List[PublicationBlock]:
    """Set block positions to match the given id order (0-based, contiguous)."""
    existing: List[PublicationBlock] = list(
        PublicationBlock.objects.filter(publication=publication)
    )
    blocks_by_id = {block.id: block for block in existing}
    if set(blocks_by_id.keys()) != {_coerce_id(bid, blocks_by_id) for bid in ordered_block_ids}:
        raise ValidationError("Reorder must list every block exactly once.")

    reordered: List[PublicationBlock] = []
    for position, block_id in enumerate(ordered_block_ids):
        block = blocks_by_id[_coerce_id(block_id, blocks_by_id)]
        block.position = position
        reordered.append(block)

    PublicationBlock.objects.bulk_update(reordered, ["position"])
    return reordered


def can_access_block_file(user: Any, publication: Publication) -> bool:
    """Whether a caller may download a block's file.

    A PUBLISHED resource's files are world-readable; a DRAFT's files are private
    to the owner, org members, and superusers — never reachable anonymously.
    """
    if is_publication_published(publication):
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if publication.user and publication.user == user:
        return True
    if publication.organization:
        from authorization.models import OrganizationMembership

        return OrganizationMembership.objects.filter(
            user=user, organization=publication.organization
        ).exists()
    return False


def _next_position(publication: Publication) -> int:
    """The position for a new block appended to the end."""
    return publication.blocks.count()


def _renumber_blocks(publication: Publication) -> None:
    """Rewrite positions to a dense 0..n-1 sequence in current order."""
    blocks: List[PublicationBlock] = list(
        PublicationBlock.objects.filter(publication=publication).order_by("position")
    )
    for position, block in enumerate(blocks):
        block.position = position
    PublicationBlock.objects.bulk_update(blocks, ["position"])


def _coerce_id(block_id: Any, blocks_by_id: dict) -> Any:
    """Match an incoming id (possibly a string) to a stored block key."""
    if block_id in blocks_by_id:
        return block_id
    for key in blocks_by_id:
        if str(key) == str(block_id):
            return key
    return block_id
