# Indexed Dataset Data API

This document describes the HTTP endpoints and SDK methods for fetching the
*indexed tabular data* that DataSpace stores in the `data_db` PostgreSQL
database. When a CSV / XLSX / Parquet / JSON resource is uploaded, its rows are
indexed into a per-resource table so they can be queried, filtered, and
streamed without re-downloading the source file.

## Overview

| Layer | Surface |
|-------|---------|
| Backend utility | `api.utils.data_indexing.fetch_resource_data(...)` |
| HTTP API | `GET /api/resources/<resource_id>/data/`, `GET /api/datasets/<dataset_id>/data/`, `GET /api/datasets/<dataset_id>/prompts/` |
| Python SDK | `DatasetClient.get_resource_data(...)`, `get_dataset_data(...)`, `get_prompt_data(...)`, `iter_resource_data(...)` |

All three endpoints share the same query-parameter contract. The prompt
endpoint adds prompt-specific shorthands.

## Permissions

- **PUBLISHED** datasets are publicly readable.
- **DRAFT / ARCHIVED** datasets require the requesting user to be the dataset
  owner, a superuser, or a member of the dataset's organization.

## HTTP API

### `GET /api/resources/<resource_id>/data/`

Returns indexed data for a single resource.

### `GET /api/datasets/<dataset_id>/data/`

Returns indexed data for a dataset. Defaults to the dataset's first indexed
resource. Use `?resource_id=<uuid>` to target a specific resource.

### `GET /api/datasets/<dataset_id>/prompts/`

Same semantics as `/data/`, but the dataset must be of `dataset_type=PROMPT`
and the response includes the auto-detected prompt / response / length column
names. Convenience filters:

| Param | Maps to |
|-------|---------|
| `prompt_contains=<str>` | `<prompt_col>__icontains=<str>` |
| `response_contains=<str>` | `<response_col>__icontains=<str>` |
| `min_length=<int>` | `<length_col>__gte=<int>` |
| `max_length=<int>` | `<length_col>__lte=<int>` |

Auto-detected columns (case-insensitive, first match wins):

- prompt: `prompt`, `input`, `instruction`, `question`
- response: `response`, `completion`, `answer`, `output`
- length: `length`, `prompt_length`, `tokens`, `token_count`

If a candidate column is not present in the resource schema, the corresponding
shorthand is silently ignored. You can always fall back to the explicit
`<col>__<op>` form.

### Query parameters

Reserved (not interpreted as filters):

| Param | Default | Notes |
|-------|---------|-------|
| `columns` | all | Comma-separated list of columns to project. |
| `limit` | `100` | Capped at `10000`. |
| `offset` | `0` | |
| `order_by` | none | Comma-separated. Prefix with `-` for DESC. |
| `count` | `true` | Set `false` to skip the `SELECT COUNT(*)` round-trip. |
| `resource_id` | first indexed | Only on `/datasets/<id>/data/` and `/prompts/`. |

Any other query param is treated as a column filter.

### Filter operators

Filters use Django-ORM-style suffixes: `?<col>__<op>=<value>`. Without a
suffix, equality is assumed: `?<col>=<value>`.

| Operator | SQL | Notes |
|----------|-----|-------|
| `eq` (default) | `=` | |
| `ne` | `<>` | |
| `gt`, `gte`, `lt`, `lte` | `>`, `>=`, `<`, `<=` | |
| `in` | `= ANY(...)` | Repeat the param: `?col__in=a&col__in=b` (or `?col__in=a,b`). |
| `nin` | `<> ALL(...)` | Same shape as `in`. |
| `contains` / `icontains` | `LIKE` / `ILIKE` `'%v%'` | |
| `startswith` / `istartswith` | `LIKE` / `ILIKE` `'v%'` | |
| `endswith` / `iendswith` | `LIKE` / `ILIKE` `'%v'` | |
| `isnull` | `IS NULL` (truthy) / `IS NOT NULL` (falsy) | Value is parsed as bool. |
| `notnull` | inverse of `isnull` | |

Unknown columns or unknown operators return HTTP **400** with a
`{"error": "..."}` body. All identifiers are quoted via `psycopg2.sql`; values
are bound as parameters — there is no string concatenation into the SQL.

### Response shape

```json
{
  "resource_id": "f1e2...",
  "dataset_id": "abcd...",
  "available_columns": ["id", "name", "price", "category"],
  "max_limit": 10000,
  "columns": ["id", "name"],
  "rows": [[1, "alpha"], [2, "beta"]],
  "total": 87,
  "limit": 100,
  "offset": 0
}
```

The prompt endpoint additionally returns:

```json
{
  "dataset_type": "PROMPT",
  "prompt_column": "prompt",
  "response_column": "response",
  "length_column": "tokens"
}
```

Set `?count=false` to avoid the count query for large tables; `total` will be
`null`.

### Examples

```bash
# Books over $10, sorted by descending price, page 2
curl "https://api.example.com/api/resources/<rid>/data/?\
category=books&price__gte=10&order_by=-price&limit=50&offset=50"

# Multiple categories
curl "https://api.example.com/api/resources/<rid>/data/?\
category__in=books&category__in=media"

# Prompt dataset: long English translation prompts
curl "https://api.example.com/api/datasets/<did>/prompts/?\
prompt_contains=translate&min_length=50&language=en"
```

## Python SDK

```python
from dataspace_sdk import DataSpaceClient

client = DataSpaceClient(
    base_url="https://dataspace.civicdatalab.in",
    keycloak_url="https://opub-kc.civicdatalab.in",
    keycloak_realm="DataSpace",
    keycloak_client_id="dataspace",
)
client.login(username="...", password="...")
```

### `get_resource_data`

```python
page = client.datasets.get_resource_data(
    resource_id="f1e2...",
    filters={
        "price__gte": 10,
        "category__in": ["books", "media"],
        "is_active": True,
    },
    columns=["id", "title", "price"],
    order_by=["-price", "title"],
    limit=200,
    offset=0,
    count=True,
)
print(page["total"], len(page["rows"]))
```

### `get_dataset_data`

Same parameters as `get_resource_data`, plus an optional `resource_id`.
Without `resource_id`, the dataset's first indexed resource is used.

```python
page = client.datasets.get_dataset_data(
    dataset_id="abcd...",
    resource_id="optional-uuid",
    filters={"region": "south"},
)
```

### `get_prompt_data`

Adds prompt-aware shorthands on top of the generic interface:

```python
page = client.datasets.get_prompt_data(
    dataset_id="abcd...",
    prompt_contains="translate",
    response_contains="bonjour",
    min_length=20,
    max_length=400,
    filters={"language": "fr"},
    columns=["prompt", "response", "tokens"],
    order_by=["-tokens"],
)
print(page["prompt_column"], page["response_column"], page["length_column"])
```

### `iter_resource_data` — streaming all rows

Transparently pages through the entire filtered result set, yielding each row
as a `{column: value}` dict. The server caps `batch_size` at `10000`.

```python
for row in client.datasets.iter_resource_data(
    resource_id="f1e2...",
    filters={"is_active": True},
    columns=["id", "title", "price"],
    batch_size=2000,
):
    process(row)
```

## Backend utility

When you need to fetch indexed data from inside the Django process (e.g. a
GraphQL resolver or background task), call the underlying utility directly:

```python
from api.models import Resource
from api.utils.data_indexing import fetch_resource_data, DataFetchError

resource = Resource.objects.get(id=resource_id)
try:
    result = fetch_resource_data(
        resource=resource,
        filters={"price__gte": 10},
        columns=["id", "title", "price"],
        order_by=["-price"],
        limit=100,
        offset=0,
        count=True,
    )
except DataFetchError as e:
    # Unknown column / no indexed table / etc.
    raise
```

The utility validates every column against `ResourceSchema` (or the live
`information_schema` if no schema rows exist) and uses parameterised queries
exclusively — passing a malicious column name returns `DataFetchError`,
never a SQL injection.

## Safety notes

- Identifiers are quoted via `psycopg2.sql.Identifier`; values are passed as
  query parameters. There is no string interpolation of user input into SQL.
- `statement_timeout` is set to **10 seconds** on every fetch.
- `limit` is clamped to **10000** rows. Use `iter_resource_data` to stream
  larger result sets.
- The `data_db` connection is read-only from this layer's perspective — the
  utility never executes anything other than `SELECT` / `SET statement_timeout`.

## Related

- [SDK overview](sdk/OVERVIEW.md)
- [SDK quick start](sdk/QUICKSTART.md)
- [Unified search API](unified_search_api.md)
