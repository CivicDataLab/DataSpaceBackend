"""
publication_uploads
────────────────────
Server-side validation for a content block's uploaded file.

``validate_publication_file`` is the upload boundary guard: it enforces the
allowed extensions, the 50 MB per-file cap, and — for a file declaring itself a
PDF — that the bytes really start with the PDF magic number (so a renamed
executable can't sneak in as ``report.pdf``). Raises a clean ValidationError on
any violation; returns the detected extension and byte size on success.
"""

import os
from typing import Any, Tuple

from django.core.exceptions import ValidationError

# Locked limits (plan §Shared context item 10).
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_FILE_SIZE_LABEL = "50 MB"
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".odp",
    ".odt",
    ".key",
}
_PDF_MAGIC = b"%PDF"


def validate_publication_file(uploaded_file: Any) -> Tuple[str, int]:
    """Validate an uploaded content-block file and return (extension, size_bytes).

    Rejects a disallowed extension, a file over the 50 MB cap, and a file that
    claims a ``.pdf`` name but whose first bytes aren't the PDF magic number.
    """
    name = getattr(uploaded_file, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"'{extension or name}' is not an allowed file type. "
            f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    size = getattr(uploaded_file, "size", 0) or 0
    if size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File is larger than the {MAX_FILE_SIZE_LABEL} limit.")

    if extension == ".pdf" and not _looks_like_pdf(uploaded_file):
        raise ValidationError("File claims to be a PDF but its contents are not.")

    return extension, size


def _looks_like_pdf(uploaded_file: Any) -> bool:
    """Peek at the first bytes to confirm a real PDF, then rewind the file."""
    try:
        uploaded_file.seek(0)
        head = uploaded_file.read(len(_PDF_MAGIC))
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        return False
    if isinstance(head, str):
        head = head.encode("latin-1", errors="ignore")
    return bool(head.startswith(_PDF_MAGIC))
