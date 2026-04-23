# Unified Search API

## Overview

The Unified Search API provides a single endpoint to search across datasets, usecases, and AI models simultaneously. Unlike individual search endpoints that search only one entity type, this API uses Elasticsearch's multi-index search capability to return properly ranked results across all entity types.

## Endpoint

```
GET /api/search/unified/
```

## Key Features

1. **Multi-Index Search**: Searches across multiple Elasticsearch indices simultaneously
2. **Relevance-Based Ranking**: Results are ranked by Elasticsearch's relevance score across all types
3. **Unified Query**: Single query syntax works across all entity types
4. **Type Filtering**: Optionally filter which entity types to search
5. **Aggregations**: Returns faceted search data for filtering
6. **Pagination**: Properly paginated results across all types

## Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | "" | Search query string |
| `page` | integer | 1 | Page number for pagination |
| `size` | integer | 10 | Number of results per page |
| `types` | string | "dataset,usecase,aimodel" | Comma-separated list of entity types to search |
| `tags` | string | - | Filter by tags (comma-separated for multiple) |
| `sectors` | string | - | Filter by sectors (comma-separated) |
| `geographies` | string | - | Filter by geographies (comma-separated, includes descendants) |
| `status` | string | - | Filter by status |

## Example Requests

### 1. Search all types with a query

```bash
GET /api/search/unified/?query=health&size=20
```

### 2. Search only datasets and usecases

```bash
GET /api/search/unified/?query=education&types=dataset,usecase
```

### 3. Search with filters

```bash
GET /api/search/unified/?query=covid&tags=health,pandemic&sectors=Healthcare
```

### 4. Search with pagination

```bash
GET /api/search/unified/?query=data&page=2&size=15
```

## Response Format

```json
{
  "results": [
    {
      "id": "uuid-or-id",
      "type": "dataset|usecase|aimodel",
      "title": "Result Title",
      "description": "Result description",
      "slug": "result-slug",
      "created": "2024-01-01T00:00:00Z",
      "modified": "2024-01-01T00:00:00Z",
      "status": "PUBLISHED",
      "tags": ["tag1", "tag2"],
      "sectors": ["sector1"],
      "geographies": ["geography1"],
      "organization": {
        "name": "Organization Name",
        "logo": "logo-url"
      },
      "user": {
        "name": "User Name",
        "bio": "User bio",
        "profile_picture": "profile-url"
      },
      "_score": 1.234,
      "_index": "index-name",

      // Type-specific fields
      // For datasets:
      "formats": ["CSV", "JSON"],
      "has_charts": true,
      "download_count": 100,
      "is_individual_dataset": false,

      // For usecases:
      "running_status": "ACTIVE",
      "logo": "logo-url",
      "is_individual_usecase": false,

      // For AI models:
      "name": "model-name",
      "display_name": "Model Display Name",
      "model_type": "LLM",
      "provider": "OpenAI",
      "is_individual_model": false
    }
  ],
  "total": 150,
  "aggregations": {
    "types": {
      "dataset": 80,
      "usecase": 50,
      "aimodel": 20
    },
    "tags": {
      "health": 45,
      "education": 30,
      "climate": 25
    },
    "sectors": {
      "Healthcare": 40,
      "Education": 35
    },
    "geographies": {
      "India": 100,
      "Maharashtra": 30
    },
    "status": {
      "PUBLISHED": 120,
      "DRAFT": 30
    }
  },
  "types_searched": ["dataset", "usecase", "aimodel"]
}
```

## How It Works

### 1. Multi-Index Search

The API searches across multiple Elasticsearch indices simultaneously:
- `search.documents.dataset_document`
- `search.documents.usecase_document`
- `search.documents.aimodel_document`

### 2. Unified Query Building

The query is built to work across all document types using:
- **Multi-match queries** on common fields (title, name, display_name, description, summary, tags)
- **Nested queries** with `ignore_unmapped=True` for type-specific fields
- **Field boosting** to prioritize title/name matches (^3) over descriptions (^2)

### 3. Relevance Ranking

Elasticsearch automatically ranks results by relevance score across all indices, ensuring the most relevant results appear first regardless of their type.

### 4. Result Normalization

Results from different indices are normalized to a common format:
- UseCase `summary` → `description`
- AIModel `display_name` or `name` → `title`
- AIModel `created_at`/`updated_at` → `created`/`modified`

## Advantages Over Individual Search APIs

1. **Better User Experience**: Users get the most relevant results across all types in a single request
2. **Proper Ranking**: Results are ranked by relevance, not grouped by type
3. **Efficient**: Single Elasticsearch query instead of multiple queries
4. **Consistent Pagination**: Pagination works correctly across all types
5. **Unified Aggregations**: Facets reflect data across all searched types

## Implementation Details

### Key Methods

- `_get_index_names()`: Maps entity types to Elasticsearch index names
- `_build_unified_query()`: Builds a query that works across all document types
- `_apply_filters()`: Applies filters compatible with all indices
- `_normalize_result()`: Normalizes results to a common format
- `perform_unified_search()`: Main search execution method

### Search Fields

**Common fields** (all types):
- title, name, display_name (boosted 3x)
- description, summary (boosted 2x)
- tags (boosted 2x)
- organization.name, user.name

**Dataset-specific**:
- resources.name, resources.description

**UseCase-specific**:
- datasets.title, datasets.description
- contributors.name

**AIModel-specific**:
- provider_model_id

## Usage in Frontend

```typescript
// Example fetch call
const response = await fetch(
  `/api/search/unified/?query=${encodeURIComponent(searchQuery)}&page=${page}&size=20`
);
const data = await response.json();

// Access results
data.results.forEach(result => {
  console.log(`${result.type}: ${result.title}`);
});

// Use aggregations for filters
const typeFilters = data.aggregations.types;
const tagFilters = data.aggregations.tags;
```

## Performance Considerations

1. **Index Size**: Performance scales with the total size of all indices
2. **Query Complexity**: Complex queries with many nested fields may be slower
3. **Aggregations**: Aggregations add overhead but are cached by Elasticsearch
4. **Pagination**: Deep pagination (high page numbers) may be slower

## Future Enhancements

- [ ] Add sorting options (relevance, date, popularity)
- [ ] Support for more advanced filters (date ranges, numeric ranges)
- [ ] Highlighting of matched terms in results
- [ ] Suggestions/autocomplete endpoint
- [ ] Export search results
- [ ] Search analytics and tracking
