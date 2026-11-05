"""Unit tests for the SQL-builder / filter helpers in
``api.utils.data_indexing`` and the request-parsing helpers in
``api.views.dataset_data``.

These tests deliberately avoid touching the actual ``data_db`` connection —
they validate the logic that turns user input into safe SQL fragments and
into normalised filter dicts.
"""

import unittest

from django.http import QueryDict
from psycopg2 import sql as pg_sql

from api.utils.data_indexing import (
    DataFetchError,
    _build_order_by,
    _build_where_clause,
    _parse_filter_key,
)
from api.views.dataset_data import _extract_filters, _parse_bool, _parse_int


def _render(composable: pg_sql.Composable) -> str:
    """Stringify a Composable without needing a live DB connection.

    Walks the Composed tree and concatenates the literal strings of each
    leaf (SQL/Identifier). Identifiers are rendered as ``"name"``.
    """
    if isinstance(composable, pg_sql.SQL):
        return composable.string
    if isinstance(composable, pg_sql.Identifier):
        # psycopg2 may store multiple components for schema-qualified idents
        parts = (
            composable.strings
            if hasattr(composable, "strings")
            else (composable._wrapped if hasattr(composable, "_wrapped") else [])
        )
        return ".".join(f'"{p}"' for p in parts)
    if isinstance(composable, pg_sql.Composed):
        return "".join(_render(c) for c in composable.seq)
    if isinstance(composable, pg_sql.Placeholder):
        return "%s"
    return str(composable)


class TestParseFilterKey(unittest.TestCase):
    def test_no_op_defaults_to_eq(self) -> None:
        self.assertEqual(_parse_filter_key("price"), ("price", "eq"))

    def test_known_op_split(self) -> None:
        self.assertEqual(_parse_filter_key("price__gte"), ("price", "gte"))
        self.assertEqual(_parse_filter_key("name__icontains"), ("name", "icontains"))

    def test_unknown_op_treated_as_column(self) -> None:
        # Column may legitimately contain "__" — if suffix isn't a known op,
        # fall back to equality on the full key.
        col, op = _parse_filter_key("weird__suffix")
        self.assertEqual((col, op), ("weird__suffix", "eq"))


class TestBuildWhereClause(unittest.TestCase):
    allowed = ["id", "price", "name", "active"]

    def test_empty_filters(self) -> None:
        sql, params = _build_where_clause({}, self.allowed)
        self.assertEqual(params, [])
        self.assertEqual(_render(sql), "")

    def test_eq_and_gte(self) -> None:
        sql, params = _build_where_clause({"price__gte": 10, "name": "abc"}, self.allowed)
        rendered = _render(sql)
        self.assertIn(" WHERE ", rendered)
        self.assertIn('"price" >= %s', rendered)
        self.assertIn('"name" = %s', rendered)
        self.assertIn(10, params)
        self.assertIn("abc", params)

    def test_in_operator_normalises_to_list(self) -> None:
        sql, params = _build_where_clause({"id__in": ("a", "b")}, self.allowed)
        rendered = _render(sql)
        self.assertIn("= ANY(%s)", rendered)
        self.assertEqual(params, [["a", "b"]])

    def test_isnull_truthy(self) -> None:
        sql, params = _build_where_clause({"name__isnull": True}, self.allowed)
        rendered = _render(sql)
        self.assertIn("IS NULL", rendered)
        self.assertEqual(params, [])

    def test_isnull_false_means_not_null(self) -> None:
        sql, _ = _build_where_clause({"name__isnull": "false"}, self.allowed)
        self.assertIn("IS NOT NULL", _render(sql))

    def test_unknown_column_rejected(self) -> None:
        with self.assertRaises(DataFetchError):
            _build_where_clause({"evil__gte": 1}, self.allowed)

    def test_icontains_wraps_value(self) -> None:
        _, params = _build_where_clause({"name__icontains": "foo"}, self.allowed)
        self.assertEqual(params, ["%foo%"])

    def test_startswith_wraps_value(self) -> None:
        _, params = _build_where_clause({"name__startswith": "foo"}, self.allowed)
        self.assertEqual(params, ["foo%"])


class TestBuildOrderBy(unittest.TestCase):
    allowed = ["id", "price"]

    def test_none_returns_empty(self) -> None:
        sql = _build_order_by(None, self.allowed)
        self.assertEqual(_render(sql), "")

    def test_asc_and_desc(self) -> None:
        sql = _build_order_by(["-price", "id"], self.allowed)
        rendered = _render(sql)
        self.assertIn(" ORDER BY ", rendered)
        self.assertIn('"price" DESC', rendered)
        self.assertIn('"id" ASC', rendered)

    def test_unknown_column_rejected(self) -> None:
        with self.assertRaises(DataFetchError):
            _build_order_by(["evil"], self.allowed)


class TestViewQueryParamHelpers(unittest.TestCase):
    def test_parse_bool(self) -> None:
        self.assertTrue(_parse_bool("true"))
        self.assertTrue(_parse_bool("YES"))
        self.assertTrue(_parse_bool(True))
        self.assertFalse(_parse_bool("0"))
        self.assertFalse(_parse_bool(None, default=False))
        self.assertTrue(_parse_bool(None, default=True))

    def test_parse_int(self) -> None:
        self.assertEqual(_parse_int("42", 0), 42)
        self.assertEqual(_parse_int(None, 7), 7)
        self.assertEqual(_parse_int("not-a-number", 9), 9)

    def test_extract_filters_skips_reserved(self) -> None:
        qd = QueryDict(mutable=True)
        qd.update({"limit": "10", "offset": "0", "columns": "a,b"})
        qd["price__gte"] = "5"
        qd["name"] = "abc"
        result = _extract_filters(qd)
        self.assertEqual(result, {"price__gte": "5", "name": "abc"})

    def test_extract_filters_in_collapses_to_list(self) -> None:
        qd = QueryDict("col__in=a&col__in=b&col__in=c,d")
        result = _extract_filters(qd)
        self.assertIn("col__in", result)
        self.assertEqual(sorted(result["col__in"]), ["a", "b", "c", "d"])

    def test_extract_filters_custom_reserved(self) -> None:
        qd = QueryDict("limit=10&prompt_contains=x&col=y")
        result = _extract_filters(
            qd,
            reserved={
                "limit",
                "offset",
                "columns",
                "order_by",
                "count",
                "resource_id",
                "format",
                "prompt_contains",
            },
        )
        self.assertEqual(result, {"col": "y"})


if __name__ == "__main__":
    unittest.main()
