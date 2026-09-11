"""
publication_download_view
──────────────────────────
Serves a content block's file through an access gate instead of a plain public
media URL, so a DRAFT resource's files are never world-readable. A published
resource's files are open; a draft's are limited to its owner / org members.
Each successful download bumps the parent resource's ``download_count``. PDFs
are served inline (for the detail-page viewer); every other type downloads.

This is a flow file: the gate and block lookup live in
``api/services/publication_blocks.py``.
"""

import os
from typing import Any

from django.db.models import F
from django.http import HttpRequest, HttpResponse, JsonResponse

from api.models import Publication, PublicationBlock
from api.services.publication_blocks import can_access_block_file
from api.utils.enums import PublicationBlockType

# Extensions we serve inline in the browser; everything else downloads.
_INLINE_CONTENT_TYPES = {".pdf": "application/pdf"}


def publication_block_download(request: HttpRequest, block_id: Any) -> HttpResponse:
    """Serve a block's file if the caller may see its resource, else 404."""
    # Find the block and its parent resource.
    try:
        block: PublicationBlock = PublicationBlock.objects.select_related("publication").get(
            id=block_id
        )
    except PublicationBlock.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    publication = block.publication

    # Gate: a draft's files are private — hide existence with a 404 on denial.
    if not can_access_block_file(request.user, publication):
        return JsonResponse({"error": "Not found"}, status=404)

    # Only file blocks have something to download.
    if block.block_type != PublicationBlockType.FILE or not block.file:
        return JsonResponse({"error": "Not found"}, status=404)

    # Count the download against the resource (race-safe increment).
    Publication.objects.filter(id=publication.id).update(download_count=F("download_count") + 1)

    # Serve the bytes inline for a PDF, as an attachment otherwise.
    return _build_file_response(block)


def _build_file_response(block: PublicationBlock) -> HttpResponse:
    """Build the HTTP file response with the right content type and disposition."""
    stored_name = block.file.name or ""
    extension = os.path.splitext(stored_name)[1].lower()
    content_type = _INLINE_CONTENT_TYPES.get(extension, "application/octet-stream")
    disposition = "inline" if extension in _INLINE_CONTENT_TYPES else "attachment"

    filename = block.file_name or os.path.basename(stored_name)
    response = HttpResponse(block.file.read(), content_type=content_type)
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response
