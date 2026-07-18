"""Layer 2 tests for the content-block file validator."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from api.utils.publication_uploads import MAX_FILE_SIZE_BYTES, validate_publication_file


def _file(name, content=b"data", content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class TestValidatePublicationFile:
    def test_accepts_an_allowed_document(self):
        extension, size = validate_publication_file(_file("brief.docx", b"x" * 10))
        assert extension == ".docx"
        assert size == 10

    def test_accepts_a_real_pdf(self):
        extension, _ = validate_publication_file(_file("report.pdf", b"%PDF-1.7 body"))
        assert extension == ".pdf"

    def test_rejects_a_disallowed_extension(self):
        for name in ("malware.exe", "archive.zip", "data.csv"):
            with pytest.raises(ValidationError):
                validate_publication_file(_file(name))

    def test_rejects_a_file_over_the_cap(self):
        oversized = _file("big.pdf", b"%PDF" + b"0" * MAX_FILE_SIZE_BYTES)
        with pytest.raises(ValidationError, match="50 MB"):
            validate_publication_file(oversized)

    def test_rejects_a_pdf_that_is_not_really_a_pdf(self):
        with pytest.raises(ValidationError, match="not"):
            validate_publication_file(_file("fake.pdf", b"MZ this is an exe"))
