"""Regression test for long text fields failing to index.

Use case and collaborative summaries are rich-text JSON documents of up to
200,000 characters, and AI model descriptions, publication descriptions and user
bios have no length limit either. Their ``raw`` sub-fields used the ``keyword``
analyzer, which emits the whole value as one token, and Lucene rejects any token
over 32,766 bytes. Elasticsearch then refused the whole document with an
"immense term" error, so the record never reached search.

Nothing queries these sub-fields, so they are gone. The fields themselves stay
indexed: search results return them and text queries match on them. The publisher
``description`` is included because the user index fills it from ``bio``.
"""

import pytest
from django.core.cache import cache

from api.views.search_usecase import SearchUseCase
from search.documents.aimodel_document import AIModelDocument
from search.documents.collaborative_document import CollaborativeDocument
from search.documents.dataset_document import DatasetDocument
from search.documents.publication_document import PublicationDocument
from search.documents.publisher_document import (
    OrganizationPublisherDocument,
    UserPublisherDocument,
)
from search.documents.usecase_document import UseCaseDocument

LONG_TEXT_FIELDS = [
    (UseCaseDocument, "summary"),
    (CollaborativeDocument, "summary"),
    (DatasetDocument, "description"),
    (AIModelDocument, "description"),
    (PublicationDocument, "description"),
    (OrganizationPublisherDocument, "description"),
    (OrganizationPublisherDocument, "bio"),
    (UserPublisherDocument, "description"),
    (UserPublisherDocument, "bio"),
]


@pytest.mark.parametrize("document,field", LONG_TEXT_FIELDS)
def test_long_text_field_has_no_single_token_subfield(document, field):
    mapping = document._doc_type.mapping.to_dict()["properties"][field]

    assert "raw" not in mapping.get("fields", {})


@pytest.mark.parametrize("document,field", LONG_TEXT_FIELDS)
def test_long_text_field_stays_searchable(document, field):
    mapping = document._doc_type.mapping.to_dict()["properties"][field]

    assert mapping["type"] == "text"
    assert mapping["analyzer"] == "html_strip"


@pytest.mark.django_db
def test_usecase_search_matches_on_summary():
    cache.delete("usecase_search_metadata_config")

    searchable_fields, _ = SearchUseCase().get_searchable_and_aggregations()

    assert "summary" in searchable_fields
