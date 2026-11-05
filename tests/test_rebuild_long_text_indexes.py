"""Migration 0054 rebuilds only search indexes that still have a single-token copy."""

import importlib
from unittest import mock

from django.test import override_settings

migration = importlib.import_module("api.migrations.0054_rebuild_long_text_search_indexes")

OLD = {
    "properties": {
        "summary": {
            "type": "text",
            "fields": {"raw": {"type": "text", "analyzer": "keyword"}},
        }
    }
}
CLEAN = {
    "properties": {
        "summary": {"type": "text", "analyzer": "html_strip"},
        "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
    }
}
NAMES = {"a": "usecase", "b": "dataset", "c": "event"}


def _run(mappings):
    es = mock.MagicMock()
    es.options.return_value = es
    es.indices.exists.side_effect = lambda index: index in mappings
    es.indices.get_mapping.side_effect = lambda index: {index: {"mappings": mappings[index]}}
    indices = {name: mock.MagicMock(_name=name) for name in NAMES.values()}
    with (
        override_settings(ELASTICSEARCH_INDEX_NAMES=NAMES),
        mock.patch("elasticsearch_dsl.connections.connections.get_connection", return_value=es),
        mock.patch(
            "django_elasticsearch_dsl.registries.registry.get_indices",
            return_value=list(indices.values()),
        ),
    ):
        migration.rebuild_long_text_indexes(None, None)
    return es, indices


def test_old_index_is_dropped_and_created_again():
    es, indices = _run({"usecase": OLD, "dataset": CLEAN})

    es.indices.delete.assert_called_once_with(index="usecase")
    indices["usecase"].create.assert_called_once()
    indices["dataset"].create.assert_not_called()


def test_nested_single_token_copy_is_found():
    nested = {"properties": {"datasets": {"type": "nested", "properties": OLD["properties"]}}}

    es, _ = _run({"dataset": nested})

    es.indices.delete.assert_called_once_with(index="dataset")


def test_clean_or_missing_indexes_are_left_alone():
    es, indices = _run({"usecase": CLEAN})

    es.indices.delete.assert_not_called()
    assert not any(index.create.called for index in indices.values())


def test_search_errors_never_fail_the_migration():
    with mock.patch(
        "elasticsearch_dsl.connections.connections.get_connection",
        side_effect=ConnectionError("down"),
    ):
        migration.rebuild_long_text_indexes(None, None)
